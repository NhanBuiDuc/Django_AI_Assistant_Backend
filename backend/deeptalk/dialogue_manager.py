# backend/deeptalk/dialogue_manager.py
from typing import Dict, List, Any, Optional
from enum import Enum
from dataclasses import dataclass
from django.utils import timezone
import json


class ConversationState(Enum):
    """Conversation states for dialogue management"""
    IDLE = "idle"
    COLLECTING_TASK_DETAILS = "collecting_task_details"
    CONFIRMING_SCHEDULE = "confirming_schedule"
    RESOLVING_CONFLICT = "resolving_conflict"
    CLARIFYING_INTENT = "clarifying_intent"
    PROVIDING_SUGGESTIONS = "providing_suggestions"


class UserIntent(Enum):
    """User intent classification"""
    CREATE_TASK = "create_task"
    SCHEDULE_EVENT = "schedule_event"
    CREATE_REMINDER = "create_reminder"
    QUERY_SCHEDULE = "query_schedule"
    MODIFY_TASK = "modify_task"
    DELETE_TASK = "delete_task"
    GET_SUGGESTIONS = "get_suggestions"
    CASUAL_CHAT = "casual_chat"


@dataclass
class ConversationContext:
    """Context tracking for ongoing conversations"""
    user_id: str
    session_id: str
    current_state: ConversationState
    current_intent: Optional[UserIntent]
    pending_task_data: Dict[str, Any]
    conversation_history: List[Dict[str, str]]
    last_interaction: timezone.datetime
    clarification_needed: Optional[str]
    suggested_actions: List[Dict[str, Any]]


class DialogueManager:
    """Advanced dialogue management with context tracking"""
    
    def __init__(self):
        self.active_sessions: Dict[str, ConversationContext] = {}
        self.context_timeout_minutes = 30
    
    def get_or_create_context(self, user_id: str, session_id: str = None) -> ConversationContext:
        """Get existing context or create new one"""
        if not session_id:
            session_id = f"{user_id}_{timezone.now().timestamp()}"
        
        if session_id in self.active_sessions:
            context = self.active_sessions[session_id]
            # Check if context is still valid
            time_diff = timezone.now() - context.last_interaction
            if time_diff.total_seconds() / 60 > self.context_timeout_minutes:
                # Context expired, create new one
                context = self._create_new_context(user_id, session_id)
        else:
            context = self._create_new_context(user_id, session_id)
        
        self.active_sessions[session_id] = context
        return context
    
    def _create_new_context(self, user_id: str, session_id: str) -> ConversationContext:
        """Create new conversation context"""
        return ConversationContext(
            user_id=user_id,
            session_id=session_id,
            current_state=ConversationState.IDLE,
            current_intent=None,
            pending_task_data={},
            conversation_history=[],
            last_interaction=timezone.now(),
            clarification_needed=None,
            suggested_actions=[]
        )
    
    def process_user_input(self, user_input: str, user_id: str, 
                          jarvis_response: Dict[str, Any], 
                          session_id: str = None) -> Dict[str, Any]:
        """Process user input with context awareness"""
        
        context = self.get_or_create_context(user_id, session_id)
        
        # Add to conversation history
        context.conversation_history.append({
            "timestamp": timezone.now().isoformat(),
            "user_input": user_input,
            "user_id": user_id
        })
        
        # Classify intent from jarvis response
        intent = self._classify_intent(jarvis_response, user_input)
        context.current_intent = intent
        
        # Determine next state and actions
        response = self._process_state_transition(context, jarvis_response, user_input)
        
        # Update context
        context.last_interaction = timezone.now()
        context.conversation_history.append({
            "timestamp": timezone.now().isoformat(),
            "ai_response": response.get("ai_response", ""),
            "state": context.current_state.value
        })
        
        return response
    
    def _classify_intent(self, jarvis_response: Dict[str, Any], user_input: str) -> UserIntent:
        """Classify user intent from jarvis response and input"""
        if jarvis_response.get("should_create_task"):
            return UserIntent.CREATE_TASK
        
        # Pattern matching for other intents
        user_input_lower = user_input.lower()
        
        if any(word in user_input_lower for word in ["schedule", "book", "plan"]):
            return UserIntent.SCHEDULE_EVENT
        elif any(word in user_input_lower for word in ["remind", "reminder", "alert"]):
            return UserIntent.CREATE_REMINDER
        elif any(word in user_input_lower for word in ["what", "when", "show", "list"]):
            return UserIntent.QUERY_SCHEDULE
        elif any(word in user_input_lower for word in ["change", "modify", "update", "edit"]):
            return UserIntent.MODIFY_TASK
        elif any(word in user_input_lower for word in ["delete", "remove", "cancel"]):
            return UserIntent.DELETE_TASK
        elif any(word in user_input_lower for word in ["suggest", "recommend", "help", "ideas"]):
            return UserIntent.GET_SUGGESTIONS
        else:
            return UserIntent.CASUAL_CHAT
    
    def _process_state_transition(self, context: ConversationContext, 
                                 jarvis_response: Dict[str, Any], 
                                 user_input: str) -> Dict[str, Any]:
        """Process state transitions and determine responses"""
        
        current_state = context.current_state
        intent = context.current_intent
        
        if current_state == ConversationState.IDLE:
            return self._handle_idle_state(context, jarvis_response, intent)
        
        elif current_state == ConversationState.COLLECTING_TASK_DETAILS:
            return self._handle_collecting_details(context, jarvis_response, user_input)
        
        elif current_state == ConversationState.CONFIRMING_SCHEDULE:
            return self._handle_schedule_confirmation(context, jarvis_response, user_input)
        
        elif current_state == ConversationState.RESOLVING_CONFLICT:
            return self._handle_conflict_resolution(context, jarvis_response, user_input)
        
        elif current_state == ConversationState.CLARIFYING_INTENT:
            return self._handle_intent_clarification(context, jarvis_response, user_input)
        
        elif current_state == ConversationState.PROVIDING_SUGGESTIONS:
            return self._handle_suggestions(context, jarvis_response, user_input)
        
        else:
            # Default fallback
            context.current_state = ConversationState.IDLE
            return jarvis_response
    
    def _handle_idle_state(self, context: ConversationContext, 
                          jarvis_response: Dict[str, Any], 
                          intent: UserIntent) -> Dict[str, Any]:
        """Handle idle state processing"""
        
        if intent == UserIntent.CREATE_TASK:
            if jarvis_response.get("task"):
                # Task has all required details
                task_data = jarvis_response["task"]
                
                # Check if critical details are missing
                missing_details = self._check_missing_details(task_data)
                
                if missing_details:
                    context.current_state = ConversationState.COLLECTING_TASK_DETAILS
                    context.pending_task_data = task_data
                    context.clarification_needed = missing_details[0]  # Ask for first missing detail
                    
                    return {
                        **jarvis_response,
                        "ai_response": f"{jarvis_response.get('ai_response', '')} {self._generate_clarification_question(missing_details[0])}",
                        "state": context.current_state.value,
                        "needs_clarification": True,
                        "missing_detail": missing_details[0]
                    }
                else:
                    # Task is complete, check for conflicts
                    context.current_state = ConversationState.CONFIRMING_SCHEDULE
                    return {
                        **jarvis_response,
                        "ai_response": f"{jarvis_response.get('ai_response', '')} Should I go ahead and schedule this?",
                        "state": context.current_state.value,
                        "requires_confirmation": True
                    }
            else:
                # No task data extracted, need more details
                context.current_state = ConversationState.CLARIFYING_INTENT
                return {
                    **jarvis_response,
                    "ai_response": "I'd like to help you create a task. Could you tell me more about what you need to do?",
                    "state": context.current_state.value,
                    "needs_clarification": True
                }
        
        elif intent == UserIntent.QUERY_SCHEDULE:
            # Handle schedule queries immediately
            return self._generate_schedule_query_response(context, jarvis_response)
        
        elif intent == UserIntent.GET_SUGGESTIONS:
            context.current_state = ConversationState.PROVIDING_SUGGESTIONS
            return self._generate_suggestions_response(context, jarvis_response)
        
        else:
            # Handle other intents or casual chat
            return jarvis_response
    
    def _handle_collecting_details(self, context: ConversationContext, 
                                  jarvis_response: Dict[str, Any], 
                                  user_input: str) -> Dict[str, Any]:
        """Handle collecting missing task details"""
        
        # Update pending task data with new information
        if jarvis_response.get("task"):
            new_data = jarvis_response["task"]
            context.pending_task_data.update(new_data)
        
        # Extract specific details from user input based on what we're asking for
        detail_needed = context.clarification_needed
        extracted_value = self._extract_specific_detail(user_input, detail_needed)
        
        if extracted_value:
            context.pending_task_data[detail_needed] = extracted_value
        
        # Check if we still need more details
        missing_details = self._check_missing_details(context.pending_task_data)
        
        if missing_details:
            # Still need more details
            context.clarification_needed = missing_details[0]
            return {
                "success": True,
                "ai_response": f"Great! {self._generate_clarification_question(missing_details[0])}",
                "state": context.current_state.value,
                "needs_clarification": True,
                "missing_detail": missing_details[0],
                "collected_so_far": context.pending_task_data
            }
        else:
            # All details collected, move to confirmation
            context.current_state = ConversationState.CONFIRMING_SCHEDULE
            context.clarification_needed = None
            
            return {
                "success": True,
                "should_create_task": True,
                "task": context.pending_task_data,
                "ai_response": f"Perfect! I have all the details. Here's what I'll schedule: {self._summarize_task(context.pending_task_data)}. Should I go ahead and create this?",
                "state": context.current_state.value,
                "requires_confirmation": True
            }
    
    def _handle_schedule_confirmation(self, context: ConversationContext, 
                                    jarvis_response: Dict[str, Any], 
                                    user_input: str) -> Dict[str, Any]:
        """Handle schedule confirmation"""
        
        user_input_lower = user_input.lower()
        
        if any(word in user_input_lower for word in ["yes", "ok", "sure", "go ahead", "confirm"]):
            # User confirmed, proceed with task creation
            context.current_state = ConversationState.IDLE
            
            return {
                "success": True,
                "should_create_task": True,
                "task": context.pending_task_data,
                "ai_response": "Perfect! I've scheduled that for you. Is there anything else I can help you with?",
                "state": context.current_state.value,
                "task_confirmed": True
            }
        
        elif any(word in user_input_lower for word in ["no", "cancel", "wait", "not yet"]):
            # User cancelled
            context.current_state = ConversationState.IDLE
            context.pending_task_data = {}
            
            return {
                "success": True,
                "should_create_task": False,
                "ai_response": "No problem! I've cancelled that. Let me know if you'd like to try again or if there's anything else I can help with.",
                "state": context.current_state.value,
                "task_cancelled": True
            }
        
        else:
            # User wants to modify something
            context.current_state = ConversationState.COLLECTING_TASK_DETAILS
            
            return {
                "success": True,
                "ai_response": "I understand you'd like to make some changes. What would you like to modify?",
                "state": context.current_state.value,
                "needs_clarification": True
            }
    
    def _check_missing_details(self, task_data: Dict[str, Any]) -> List[str]:
        """Check what critical details are missing from task data"""
        missing = []
        
        if not task_data.get("name") or len(task_data.get("name", "").strip()) < 3:
            missing.append("name")
        
        if not task_data.get("estimated_duration_minutes"):
            missing.append("duration")
        
        # Only require deadline for high priority tasks
        if task_data.get("base_priority", 3) <= 2 and not task_data.get("deadline"):
            missing.append("deadline")
        
        return missing
    
    def _generate_clarification_question(self, detail_type: str) -> str:
        """Generate clarification questions for missing details"""
        questions = {
            "name": "What would you like to call this task?",
            "duration": "How long do you think this will take?",
            "deadline": "When does this need to be completed?",
            "category": "What category would this fall under?",
            "priority": "How important is this task (high, medium, or low priority)?"
        }
        
        return questions.get(detail_type, f"Could you provide more details about {detail_type}?")
    
    def _extract_specific_detail(self, user_input: str, detail_type: str) -> Any:
        """Extract specific detail from user input"""
        if detail_type == "duration":
            # Look for time expressions
            import re
            time_patterns = [
                r'(\d+)\s*hours?',
                r'(\d+)\s*hrs?',
                r'(\d+)\s*minutes?',
                r'(\d+)\s*mins?'
            ]
            
            for pattern in time_patterns:
                match = re.search(pattern, user_input.lower())
                if match:
                    value = int(match.group(1))
                    if 'hour' in pattern or 'hr' in pattern:
                        return value * 60  # Convert to minutes
                    else:
                        return value
        
        elif detail_type == "name":
            # If user input looks like a task name, use it
            if len(user_input.strip()) > 3 and not any(word in user_input.lower() for word in ["when", "how", "what", "where"]):
                return user_input.strip()
        
        return None
    
    def _summarize_task(self, task_data: Dict[str, Any]) -> str:
        """Generate a summary of the task"""
        name = task_data.get("name", "Unnamed task")
        duration = task_data.get("estimated_duration_minutes", 60)
        priority = task_data.get("base_priority", 3)
        
        priority_text = ["", "critical", "high", "medium", "low", "very low"][priority]
        
        summary = f"'{name}' ({duration} minutes, {priority_text} priority)"
        
        if task_data.get("deadline"):
            summary += f" due {task_data['deadline']}"
        
        return summary
    
    def _generate_schedule_query_response(self, context: ConversationContext, 
                                        jarvis_response: Dict[str, Any]) -> Dict[str, Any]:
        """Generate response for schedule queries"""
        # This would integrate with your schedule engine to get current schedule
        return {
            **jarvis_response,
            "ai_response": "Here's your current schedule... (integrate with schedule query logic)",
            "schedule_query": True
        }
    
    def _generate_suggestions_response(self, context: ConversationContext, 
                                     jarvis_response: Dict[str, Any]) -> Dict[str, Any]:
        """Generate suggestions for the user"""
        context.current_state = ConversationState.IDLE  # Return to idle after suggestions
        
        return {
            **jarvis_response,
            "ai_response": "Based on your schedule and patterns, here are some suggestions... (integrate with suggestion engine)",
            "suggestions_provided": True
        }
    
    def get_context_summary(self, session_id: str) -> Dict[str, Any]:
        """Get summary of current conversation context"""
        if session_id in self.active_sessions:
            context = self.active_sessions[session_id]
            return {
                "state": context.current_state.value,
                "intent": context.current_intent.value if context.current_intent else None,
                "pending_data": context.pending_task_data,
                "history_length": len(context.conversation_history),
                "last_interaction": context.last_interaction.isoformat()
            }
        return {"error": "Session not found"}
    
    def clear_context(self, session_id: str) -> bool:
        """Clear conversation context"""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
            return True
        return False