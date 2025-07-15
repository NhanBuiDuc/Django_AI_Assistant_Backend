# backend/deeptalk/personalization_engine.py
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Avg, Count, Q
from collections import defaultdict, Counter
import json
import numpy as np


class PersonalizationEngine:
    """Learn and adapt to user preferences for intelligent recommendations"""
    
    def __init__(self):
        self.preference_weights = {
            'time_of_day': 0.3,
            'duration_accuracy': 0.25,
            'category_affinity': 0.2,
            'completion_patterns': 0.15,
            'scheduling_preferences': 0.1
        }
    
    def analyze_user_patterns(self, user) -> Dict[str, Any]:
        """Analyze user's historical patterns and preferences"""
        from .models import Task, TaskLog
        
        # Get user's task history
        tasks = Task.objects.filter(
            user=user, 
            deleted_at__isnull=True,
            created_at__gte=timezone.now() - timedelta(days=90)  # Last 90 days
        )
        
        patterns = {
            'preferred_times': self._analyze_time_preferences(tasks),
            'duration_accuracy': self._analyze_duration_accuracy(tasks),
            'category_preferences': self._analyze_category_affinity(tasks),
            'completion_patterns': self._analyze_completion_patterns(tasks),
            'productivity_hours': self._analyze_productivity_patterns(tasks),
            'scheduling_habits': self._analyze_scheduling_habits(tasks),
            'priority_patterns': self._analyze_priority_patterns(tasks)
        }
        
        return patterns
    
    def _analyze_time_preferences(self, tasks) -> Dict[str, Any]:
        """Analyze when user prefers to schedule different types of tasks"""
        time_preferences = defaultdict(list)
        
        for task in tasks.filter(specific_time__isnull=False):
            if task.specific_time:
                hour = task.specific_time.hour
                category = task.category.name if task.category else 'uncategorized'
                time_preferences[category].append(hour)
        
        # Calculate preferred hours for each category
        preferred_hours = {}
        for category, hours in time_preferences.items():
            if len(hours) >= 3:  # Need at least 3 data points
                preferred_hours[category] = {
                    'mean_hour': round(np.mean(hours), 1),
                    'std_hour': round(np.std(hours), 1),
                    'most_common': Counter(hours).most_common(3)
                }
        
        return {
            'category_time_preferences': preferred_hours,
            'overall_active_hours': self._get_most_active_hours(time_preferences)
        }
    
    def _analyze_duration_accuracy(self, tasks) -> Dict[str, Any]:
        """Analyze how accurate user's time estimates are"""
        estimation_accuracy = []
        
        for task in tasks.filter(
            estimated_duration_minutes__isnull=False,
            actual_time_spent_minutes__gt=0
        ):
            estimated = task.estimated_duration_minutes
            actual = task.actual_time_spent_minutes
            
            if estimated > 0:
                accuracy_ratio = actual / estimated
                estimation_accuracy.append({
                    'task_id': task.id,
                    'category': task.category.name if task.category else 'uncategorized',
                    'estimated': estimated,
                    'actual': actual,
                    'ratio': accuracy_ratio
                })
        
        if not estimation_accuracy:
            return {'insufficient_data': True}
        
        # Calculate statistics
        ratios = [item['ratio'] for item in estimation_accuracy]
        category_accuracy = defaultdict(list)
        
        for item in estimation_accuracy:
            category_accuracy[item['category']].append(item['ratio'])
        
        return {
            'overall_accuracy': {
                'mean_ratio': round(np.mean(ratios), 2),
                'median_ratio': round(np.median(ratios), 2),
                'tends_to': 'underestimate' if np.mean(ratios) > 1.2 else 'overestimate' if np.mean(ratios) < 0.8 else 'accurate'
            },
            'category_accuracy': {
                cat: {
                    'mean_ratio': round(np.mean(ratios), 2),
                    'sample_size': len(ratios)
                }
                for cat, ratios in category_accuracy.items() if len(ratios) >= 2
            }
        }
    
    def _analyze_category_affinity(self, tasks) -> Dict[str, Any]:
        """Analyze user's preference for different task categories"""
        category_stats = defaultdict(lambda: {
            'total_tasks': 0,
            'completed_tasks': 0,
            'avg_completion_time': 0,
            'satisfaction_scores': []
        })
        
        for task in tasks:
            category = task.category.name if task.category else 'uncategorized'
            stats = category_stats[category]
            
            stats['total_tasks'] += 1
            
            if task.status == 'completed':
                stats['completed_tasks'] += 1
                
                if task.user_satisfaction_rating:
                    stats['satisfaction_scores'].append(task.user_satisfaction_rating)
        
        # Calculate affinity scores
        affinity_scores = {}
        for category, stats in category_stats.items():
            if stats['total_tasks'] >= 2:  # Need at least 2 tasks
                completion_rate = stats['completed_tasks'] / stats['total_tasks']
                avg_satisfaction = np.mean(stats['satisfaction_scores']) if stats['satisfaction_scores'] else 3.0
                
                # Affinity score combines completion rate and satisfaction
                affinity_score = (completion_rate * 0.6) + (avg_satisfaction / 5.0 * 0.4)
                
                affinity_scores[category] = {
                    'affinity_score': round(affinity_score, 2),
                    'completion_rate': round(completion_rate, 2),
                    'avg_satisfaction': round(avg_satisfaction, 1),
                    'sample_size': stats['total_tasks']
                }
        
        return {
            'category_affinity': affinity_scores,
            'preferred_categories': sorted(
                affinity_scores.items(),
                key=lambda x: x[1]['affinity_score'],
                reverse=True
            )[:3]
        }
    
    def _analyze_completion_patterns(self, tasks) -> Dict[str, Any]:
        """Analyze when and how user completes tasks"""
        completion_patterns = {
            'completion_by_day': defaultdict(int),
            'completion_by_hour': defaultdict(int),
            'completion_streaks': [],
            'procrastination_patterns': []
        }
        
        completed_tasks = tasks.filter(status='completed', completed_at__isnull=False)
        
        for task in completed_tasks:
            # Day of week patterns
            day_of_week = task.completed_at.strftime('%A')
            completion_patterns['completion_by_day'][day_of_week] += 1
            
            # Hour of day patterns
            hour = task.completed_at.hour
            completion_patterns['completion_by_hour'][hour] += 1
            
            # Procrastination analysis
            if task.deadline:
                time_diff = task.deadline - task.completed_at
                hours_before_deadline = time_diff.total_seconds() / 3600
                completion_patterns['procrastination_patterns'].append(hours_before_deadline)
        
        return {
            'most_productive_days': sorted(
                completion_patterns['completion_by_day'].items(),
                key=lambda x: x[1],
                reverse=True
            )[:3],
            'most_productive_hours': sorted(
                completion_patterns['completion_by_hour'].items(),
                key=lambda x: x[1],
                reverse=True
            )[:3],
            'procrastination_tendency': self._analyze_procrastination(
                completion_patterns['procrastination_patterns']
            )
        }
    
    def _analyze_productivity_patterns(self, tasks) -> Dict[str, Any]:
        """Identify user's most and least productive periods"""
        productivity_by_hour = defaultdict(lambda: {'completed': 0, 'created': 0})
        
        # Completed tasks by hour
        for task in tasks.filter(status='completed', completed_at__isnull=False):
            hour = task.completed_at.hour
            productivity_by_hour[hour]['completed'] += 1
        
        # Created tasks by hour
        for task in tasks:
            hour = task.created_at.hour
            productivity_by_hour[hour]['created'] += 1
        
        # Calculate productivity ratios
        productivity_ratios = {}
        for hour, stats in productivity_by_hour.items():
            if stats['created'] > 0:
                ratio = stats['completed'] / stats['created']
                productivity_ratios[hour] = {
                    'completion_ratio': round(ratio, 2),
                    'completed_count': stats['completed'],
                    'created_count': stats['created']
                }
        
        # Sort by productivity
        sorted_hours = sorted(
            productivity_ratios.items(),
            key=lambda x: x[1]['completion_ratio'],
            reverse=True
        )
        
        return {
            'most_productive_hours': sorted_hours[:3],
            'least_productive_hours': sorted_hours[-3:] if len(sorted_hours) >= 3 else [],
            'productivity_by_hour': productivity_ratios
        }
    
    def _analyze_scheduling_habits(self, tasks) -> Dict[str, Any]:
        """Analyze user's scheduling habits and preferences"""
        habits = {
            'advance_planning': [],  # How far in advance user plans
            'preferred_durations': [],  # Preferred task durations
            'break_patterns': [],  # Time between tasks
            'batch_scheduling': {}  # Tendency to batch similar tasks
        }
        
        # Advance planning analysis
        for task in tasks.filter(specific_time__isnull=False):
            if task.specific_time:
                advance_time = task.specific_time - task.created_at
                advance_hours = advance_time.total_seconds() / 3600
                habits['advance_planning'].append(advance_hours)
        
        # Duration preferences
        for task in tasks:
            if task.estimated_duration_minutes:
                habits['preferred_durations'].append(task.estimated_duration_minutes)
        
        return {
            'planning_horizon': {
                'avg_advance_hours': round(np.mean(habits['advance_planning']), 1) if habits['advance_planning'] else None,
                'planning_style': self._categorize_planning_style(habits['advance_planning'])
            },
            'duration_preferences': {
                'avg_duration': round(np.mean(habits['preferred_durations']), 0) if habits['preferred_durations'] else None,
                'preferred_range': self._get_duration_range_preference(habits['preferred_durations'])
            }
        }
    
    def _analyze_priority_patterns(self, tasks) -> Dict[str, Any]:
        """Analyze how user assigns and handles priorities"""
        priority_usage = Counter(task.base_priority for task in tasks if hasattr(task, 'base_priority'))
        
        # Fallback to legacy priority field if base_priority doesn't exist
        if not priority_usage:
            priority_usage = Counter(task.priority for task in tasks)
        
        # Completion rates by priority
        priority_completion = defaultdict(lambda: {'total': 0, 'completed': 0})
        
        for task in tasks:
            priority = getattr(task, 'base_priority', task.priority)
            priority_completion[priority]['total'] += 1
            if task.status == 'completed':
                priority_completion[priority]['completed'] += 1
        
        completion_rates = {}
        for priority, stats in priority_completion.items():
            if stats['total'] > 0:
                completion_rates[priority] = round(stats['completed'] / stats['total'], 2)
        
        return {
            'priority_distribution': dict(priority_usage),
            'completion_by_priority': completion_rates,
            'priority_effectiveness': self._analyze_priority_effectiveness(completion_rates)
        }
    
    def generate_personalized_suggestions(self, user, current_tasks: List) -> Dict[str, Any]:
        """Generate personalized suggestions based on user patterns"""
        patterns = self.analyze_user_patterns(user)
        
        suggestions = {
            'scheduling_suggestions': self._generate_scheduling_suggestions(patterns, current_tasks),
            'optimization_tips': self._generate_optimization_tips(patterns),
            'habit_improvements': self._generate_habit_suggestions(patterns),
            'personalized_defaults': self._generate_personalized_defaults(patterns)
        }
        
        return suggestions
    
    def _generate_scheduling_suggestions(self, patterns: Dict, current_tasks: List) -> List[Dict]:
        """Generate scheduling suggestions based on patterns"""
        suggestions = []
        
        # Time-based suggestions
        if 'preferred_times' in patterns:
            productive_hours = patterns.get('productivity_hours', {}).get('most_productive_hours', [])
            if productive_hours:
                suggestions.append({
                    'type': 'time_optimization',
                    'message': f"Your most productive hours are {productive_hours[0][0]}:00. Consider scheduling important tasks then.",
                    'confidence': 0.8
                })
        
        # Duration suggestions
        if 'duration_accuracy' in patterns:
            accuracy = patterns['duration_accuracy']
            if not accuracy.get('insufficient_data'):
                tends_to = accuracy['overall_accuracy']['tends_to']
                if tends_to != 'accurate':
                    suggestions.append({
                        'type': 'duration_estimation',
                        'message': f"You tend to {tends_to} task durations. Consider adjusting your estimates.",
                        'confidence': 0.7
                    })
        
        return suggestions
    
    def _generate_optimization_tips(self, patterns: Dict) -> List[Dict]:
        """Generate optimization tips based on user patterns"""
        tips = []
        
        # Category affinity tips
        if 'category_preferences' in patterns:
            preferred_cats = patterns['category_preferences'].get('preferred_categories', [])
            if preferred_cats:
                tips.append({
                    'type': 'category_focus',
                    'message': f"You're most successful with {preferred_cats[0][0]} tasks. Consider prioritizing these.",
                    'confidence': 0.8
                })
        
        return tips
    
    def _generate_habit_suggestions(self, patterns: Dict) -> List[Dict]:
        """Generate habit improvement suggestions"""
        suggestions = []
        
        # Planning suggestions
        if 'scheduling_habits' in patterns:
            planning_style = patterns['scheduling_habits']['planning_horizon']['planning_style']
            if planning_style == 'last_minute':
                suggestions.append({
                    'type': 'planning_improvement',
                    'message': "Try planning tasks 24-48 hours in advance for better success rates.",
                    'confidence': 0.7
                })
        
        return suggestions
    
    def _generate_personalized_defaults(self, patterns: Dict) -> Dict[str, Any]:
        """Generate personalized default values for new tasks"""
        defaults = {}
        
        # Default duration based on category
        if 'category_preferences' in patterns:
            category_prefs = patterns['category_preferences'].get('category_affinity', {})
            duration_defaults = {}
            
            for category, stats in category_prefs.items():
                # This would need to be calculated from historical data
                duration_defaults[category] = 60  # Default fallback
            
            defaults['duration_by_category'] = duration_defaults
        
        # Default priority based on completion patterns
        if 'priority_patterns' in patterns:
            effectiveness = patterns['priority_patterns'].get('priority_effectiveness', {})
            if effectiveness:
                best_priority = max(effectiveness, key=effectiveness.get)
                defaults['suggested_priority'] = best_priority
        
        return defaults
    
    # Helper methods for analysis
    def _get_most_active_hours(self, time_preferences: Dict) -> List[int]:
        """Get the most active hours across all categories"""
        all_hours = []
        for hours_list in time_preferences.values():
            all_hours.extend(hours_list)
        
        if all_hours:
            hour_counts = Counter(all_hours)
            return [hour for hour, count in hour_counts.most_common(3)]
        return []
    
    def _analyze_procrastination(self, completion_times: List[float]) -> Dict[str, Any]:
        """Analyze procrastination patterns"""
        if not completion_times:
            return {'insufficient_data': True}
        
        avg_hours_before = np.mean(completion_times)
        
        if avg_hours_before < 6:
            tendency = 'last_minute'
        elif avg_hours_before < 24:
            tendency = 'day_of'
        elif avg_hours_before < 72:
            tendency = 'few_days_early'
        else:
            tendency = 'well_planned'
        
        return {
            'avg_hours_before_deadline': round(avg_hours_before, 1),
            'tendency': tendency,
            'sample_size': len(completion_times)
        }
    
    def _categorize_planning_style(self, advance_times: List[float]) -> str:
        """Categorize user's planning style"""
        if not advance_times:
            return 'unknown'
        
        avg_advance = np.mean(advance_times)
        
        if avg_advance < 2:
            return 'last_minute'
        elif avg_advance < 24:
            return 'same_day'
        elif avg_advance < 72:
            return 'few_days_ahead'
        else:
            return 'long_term_planner'
    
    def _get_duration_range_preference(self, durations: List[int]) -> str:
        """Get preferred duration range"""
        if not durations:
            return 'unknown'
        
        avg_duration = np.mean(durations)
        
        if avg_duration < 30:
            return 'short_tasks'  # < 30 minutes
        elif avg_duration < 90:
            return 'medium_tasks'  # 30-90 minutes
        else:
            return 'long_tasks'  # > 90 minutes
    
    def _analyze_priority_effectiveness(self, completion_rates: Dict) -> Dict[str, Any]:
        """Analyze which priorities are most effective for the user"""
        if not completion_rates:
            return {'insufficient_data': True}
        
        most_effective = max(completion_rates, key=completion_rates.get)
        least_effective = min(completion_rates, key=completion_rates.get)
        
        return {
            'most_effective_priority': most_effective,
            'least_effective_priority': least_effective,
            'effectiveness_range': round(completion_rates[most_effective] - completion_rates[least_effective], 2)
        }
    
    def update_user_preferences(self, user, new_feedback: Dict[str, Any]) -> bool:
        """Update user preferences based on new feedback"""
        try:
            from .models import UserPreferences
            
            preferences, created = UserPreferences.objects.get_or_create(user=user)
            
            # Update preferences based on feedback
            if 'preferred_duration' in new_feedback:
                preferences.default_task_duration = new_feedback['preferred_duration']
            
            if 'productive_hours' in new_feedback:
                preferences.most_productive_hours = new_feedback['productive_hours']
            
            preferences.save()
            return True
            
        except Exception as e:
            print(f"Error updating preferences: {e}")
            return False