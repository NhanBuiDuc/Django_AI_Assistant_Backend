# backend/deeptalk/ollama_task_agent.py - Updated for optimized models

import json
import requests
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from langchain.llms.base import LLM
from langchain.schema import BaseMessage, HumanMessage, SystemMessage
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field, validator
from django.utils import timezone
from decimal import Decimal
from .models import Task, TaskCategory, DeepTalkUser
from .models import TimeBlock, UserPreferences
from datetime import datetime, time, timedelta
from .models import Task, TaskCategory, DeepTalkUser
import logging
from .serializers import (
    TaskSerializer
)
logger = logging.getLogger(__name__)

class ActionIntent:
    CREATE_TASK = "create_task"
    CONTEXT_RESPONSE = "context_response"
    READ_TASK = "read_task" 
    UPDATE_TASK = "update_task"
    DELETE_TASK = "delete_task"
    GENERAL_CHAT = "general_chat"

    # def _analyze_action_intent(self, user_input: str, conversation_context: Dict = None) -> Dict[str, Any]:
    #     """Analyze what the user wants to do and if we have enough info"""
    #     user_lower = user_input.lower()
        
    #     # Detect action type
    #     if any(word in user_lower for word in ['schedule', 'create', 'add', 'new', 'remind', 'plan']):
    #         action_intent = ActionIntent.CREATE_TASK
    #         required_fields = self._get_required_fields_for_task()
    #         extracted_fields = self._extract_available_fields(user_input, conversation_context)
    #         missing_fields = self._get_missing_fields(required_fields, extracted_fields)
            
    #         if missing_fields:
    #             return {
    #                 "action_intent": ActionIntent.CONTEXT_RESPONSE,
    #                 "target_action": ActionIntent.CREATE_TASK,
    #                 "extracted_fields": extracted_fields,
    #                 "missing_fields": missing_fields,
    #                 "clarification_needed": True
    #             }
    #         else:
    #             return {
    #                 "action_intent": ActionIntent.CREATE_TASK,
    #                 "extracted_fields": extracted_fields,
    #                 "clarification_needed": False
    #             }
        
    #     elif any(word in user_lower for word in ['show', 'list', 'find', 'search', 'what', 'which']):
    #         return {"action_intent": ActionIntent.READ_TASK}
        
    #     elif any(word in user_lower for word in ['update', 'change', 'modify', 'edit', 'reschedule']):
    #         return {"action_intent": ActionIntent.UPDATE_TASK}
        
    #     elif any(word in user_lower for word in ['delete', 'remove', 'cancel', 'drop']):
    #         return {"action_intent": ActionIntent.DELETE_TASK}
        
    #     else:
    #         return {"action_intent": ActionIntent.GENERAL_CHAT}

    # def _get_required_fields_for_task(self) -> List[str]:
    #     """Define what fields we need before creating a task"""
    #     return ['name', 'estimated_duration_minutes']  # Minimum required

    # def _extract_available_fields(self, user_input: str, conversation_context: Dict = None) -> Dict:
    #     """Extract whatever fields we can from current input + context"""
    #     fields = {}
    #     user_lower = user_input.lower()
        
    #     # Extract name/title
    #     if 'meeting with' in user_lower:
    #         name_match = re.search(r'meeting with ([^,.\n]+)', user_lower)
    #         if name_match:
    #             fields['name'] = f"Meeting with {name_match.group(1).strip().title()}"
    #     elif 'call' in user_lower:
    #         call_match = re.search(r'call ([^,.\n]+)', user_lower)
    #         if call_match:
    #             fields['name'] = f"Call {call_match.group(1).strip().title()}"
    #     else:
    #         # Generic task name
    #         fields['name'] = user_input[:50] + "..." if len(user_input) > 50 else user_input
        
    #     # Extract timing
    #     if any(word in user_lower for word in ['tomorrow', 'next week', 'monday', 'tuesday']):
    #         fields['has_timing'] = True
        
    #     # Extract duration hints
    #     if 'hour' in user_lower:
    #         duration_match = re.search(r'(\d+)\s*hour', user_lower)
    #         if duration_match:
    #             fields['estimated_duration_minutes'] = int(duration_match.group(1)) * 60
    #     elif 'minute' in user_lower:
    #         duration_match = re.search(r'(\d+)\s*minute', user_lower)
    #         if duration_match:
    #             fields['estimated_duration_minutes'] = int(duration_match.group(1))
        
    #     # Merge with conversation context
    #     if conversation_context:
    #         fields.update(conversation_context.get('accumulated_fields', {}))
        
    #     return fields

    # def _get_missing_fields(self, required_fields: List[str], extracted_fields: Dict) -> List[str]:
    #     """Determine what fields are still missing"""
    #     missing = []
    #     for field in required_fields:
    #         if field not in extracted_fields:
    #             missing.append(field)
    #     return missing

    # def _generate_clarification_question(self, missing_fields: List[str], extracted_fields: Dict) -> str:
    #     """Generate a natural question to get missing information"""
    #     if 'estimated_duration_minutes' in missing_fields:
    #         if 'name' in extracted_fields:
    #             return f"Great! I'll help you with '{extracted_fields['name']}'. How long do you think this will take?"
    #         else:
    #             return "How long do you expect this to take?"
        
    #     elif 'specific_time' in missing_fields:
    #         return "When would you like to schedule this?"
        
    #     elif 'name' in missing_fields:
    #         return "What would you like to call this task?"
        
    #     else:
    #         return "Could you provide a bit more detail about what you need?"

class TaskExtraction(BaseModel):
    """Structured output for extracted task information - optimized for EDF/HPF"""
    name: str = Field(description="Clear, concise task name")
    description: str = Field(description="Detailed description of the task")
    
    # Priority fields for HPF algorithm
    base_priority: int = Field(description="Base priority level 1-5 (1=highest, 5=lowest)", ge=1, le=5, default=3)
    urgency_multiplier: float = Field(description="Urgency multiplier (0.5-3.0)", ge=0.5, le=3.0, default=1.0)
    
    # Duration fields for scheduling (in MINUTES)
    estimated_duration_minutes: int = Field(description="Estimated duration in minutes", ge=5, le=1440, default=60)  # 5 min to 24 hours
    minimum_duration_minutes: Optional[int] = Field(description="Minimum acceptable duration in minutes", ge=5, le=1440)
    maximum_duration_minutes: Optional[int] = Field(description="Maximum acceptable duration in minutes", ge=5, le=1440)
    
    # Deadline fields for EDF algorithm
    deadline: Optional[str] = Field(description="Hard deadline in ISO format (YYYY-MM-DDTHH:MM:SS)")
    preferred_completion_time: Optional[str] = Field(description="Preferred completion time in ISO format")
    deadline_flexibility_minutes: int = Field(description="How many minutes the deadline can shift", default=0, ge=0)
    
    # Scheduling constraints
    can_be_split: bool = Field(description="Whether this task can be broken into chunks", default=True)
    requires_consecutive_time: bool = Field(description="Must be done in one uninterrupted block", default=False)
    
    # Context and requirements
    category: Optional[str] = Field(description="Task category (work, personal, health, education, etc.)")
    tags: List[str] = Field(description="Relevant tags for the task", default=[])
    location: Optional[str] = Field(description="Location where task should be performed")
    required_tools: List[str] = Field(description="Tools or resources needed", default=[])
    required_energy_level: int = Field(description="Energy level required 1-5 (1=low, 5=high)", ge=1, le=5, default=3)
    
    # Time preferences
    preferred_time_of_day: List[str] = Field(description="Preferred times like ['09:00', '14:00']", default=[])
    avoid_time_of_day: List[str] = Field(description="Times to avoid like ['13:00', '17:00']", default=[])
    
    # Recurrence
    is_recurring: bool = Field(description="Whether this is a recurring task", default=False)
    recurrence_pattern: Dict[str, Any] = Field(description="Recurrence details as dict", default={})
    
    # Legacy compatibility
    difficulty_level: int = Field(description="Difficulty level 1-5 (1=easiest, 5=hardest)", ge=1, le=5, default=3)
    dependencies: List[str] = Field(description="Tasks this depends on", default=[])

class JarvisResponse(BaseModel):
    """Complete Jarvis response with both task extraction and conversational response"""
    should_create_task: bool = Field(description="Whether a task should be created from this input")
    conversational_response: str = Field(description="Natural language response to the user")
    task_data: Optional[TaskExtraction] = Field(description="Extracted task information if should_create_task is True")

class OllamaLLM:
    """Fixed LLM wrapper for Ollama"""
    
    def __init__(self, model="llama3.2:latest", ollama_url="http://localhost:11434", temperature=0.7):
        self.model = model
        self.ollama_url = ollama_url
        self.temperature = temperature
        self.available = self._test_connection()
    
    def _test_connection(self):
        """Test if Ollama is available"""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models_data = response.json()
                available_models = [m.get('name') for m in models_data.get('models', [])]
                
                if self.model not in available_models and available_models:
                    self.model = available_models[0]  # Use first available
                    logger.info(f"Using available model: {self.model}")
                
                return True
        except Exception as e:
            logger.warning(f"Ollama not available: {e}")
        return False
    
    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        """Call Ollama API - FIXED VERSION"""
        if not self.available:
            return "I'm having trouble connecting to my AI brain right now, but I can still help!"
        
        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": self.temperature,
                        "top_p": 0.9,
                        "top_k": 40
                    }
                },
                timeout=30  # Increased timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("response", "")
            else:
                logger.error(f"Ollama error: {response.status_code}")
                return ""
                
        except Exception as e:
            logger.error(f"Ollama API error: {str(e)}")
            return ""

def clean_json_response(response_text: str) -> str:
    """Clean JSON response by removing comments and extra formatting"""
    # Remove JavaScript-style comments (// comment)
    response_text = re.sub(r'//.*?(?=\n|$)', '', response_text)
    
    # Remove C-style comments (/* comment */)
    response_text = re.sub(r'/\*.*?\*/', '', response_text, flags=re.DOTALL)
    
    # Remove code block markers
    if response_text.strip().startswith("```json"):
        response_text = response_text.replace("```json", "").replace("```", "").strip()
    
    # Remove any trailing commas before closing braces/brackets
    response_text = re.sub(r',(\s*[}\]])', r'\1', response_text)
    
    # Clean up extra whitespace
    response_text = response_text.strip()
    
    return response_text

class JarvisTaskAgent:
    """Fixed AI Agent for processing natural language"""
    
    def __init__(self, ollama_url: str = None, model: str = None):
        self.model = model or "llama3.2:latest"
        self.ollama_url = ollama_url or "http://localhost:11434"
        
        # Initialize LLM
        self.llm = OllamaLLM(
            model=self.model, 
            ollama_url=self.ollama_url
        )
        
        logger.info(f"Jarvis initialized with model: {self.model}, available: {self.llm.available}")

    def process_user_input(self, user_input: str, user=None, conversation_context: Dict = None) -> Dict[str, Any]:
        """Process user input - FIXED VERSION"""
        
        if not user_input or not user_input.strip():
            return {
                "success": True,
                "action_intent": ActionIntent.GENERAL_CHAT,
                "should_create_task": False,
                "ai_response": "Hi! What can I help you with today?"
            }
        
        user_input = user_input.strip()
        
        # Simple intent detection
        intent_analysis = self._analyze_action_intent(user_input, conversation_context)
        
        if intent_analysis["action_intent"] == ActionIntent.CREATE_TASK:
            # Handle task creation
            task_data = self._extract_task_data(user_input)
            ai_response = self._generate_task_response(user_input, task_data)
            
            return {
                "success": True,
                "action_intent": ActionIntent.CREATE_TASK,
                "should_create_task": True,
                "ai_response": ai_response,
                "user_input": user_input,
                "task": task_data
            }
        
        else:
            # General conversation
            ai_response = self._get_conversational_response(user_input)
            
            return {
                "success": True,
                "action_intent": intent_analysis["action_intent"],
                "should_create_task": False,
                "ai_response": ai_response,
                "user_input": user_input
            }

    def _analyze_action_intent(self, user_input: str, conversation_context: Dict = None) -> Dict[str, Any]:
        """Analyze what the user wants to do - SIMPLIFIED"""
        user_lower = user_input.lower()
        
        # Check for task creation keywords
        create_keywords = [
            'create', 'add', 'new', 'remind', 'schedule', 'plan', 'task',
            'need to', 'have to', 'should', 'must', 'todo'
        ]
        
        if any(keyword in user_lower for keyword in create_keywords):
            return {"action_intent": ActionIntent.CREATE_TASK}
        
        # Check for other intents
        elif any(word in user_lower for word in ['show', 'list', 'find', 'what']):
            return {"action_intent": ActionIntent.READ_TASK}
        
        elif any(word in user_lower for word in ['update', 'change', 'modify', 'edit']):
            return {"action_intent": ActionIntent.UPDATE_TASK}
        
        elif any(word in user_lower for word in ['delete', 'remove', 'cancel']):
            return {"action_intent": ActionIntent.DELETE_TASK}
        
        else:
            return {"action_intent": ActionIntent.GENERAL_CHAT}

    def _extract_task_data(self, user_input: str) -> Dict:
        """Extract task data from user input - SIMPLIFIED"""
        
        # Basic task extraction
        task_name = user_input
        
        # Clean up common patterns
        patterns_to_remove = [
            r'^(create|add|new|make)\s+(a\s+)?task\s+(to\s+)?',
            r'^remind\s+me\s+to\s+',
            r'^schedule\s+',
            r'^i\s+(need|have|should|must)\s+to\s+'
        ]
        
        for pattern in patterns_to_remove:
            task_name = re.sub(pattern, '', task_name, flags=re.IGNORECASE).strip()
        
        # Limit length
        if len(task_name) > 100:
            task_name = task_name[:100]
        
        # Extract priority
        priority = 3  # Default
        if any(word in user_input.lower() for word in ['urgent', 'important', 'critical']):
            priority = 1
        elif any(word in user_input.lower() for word in ['high']):
            priority = 2
        elif any(word in user_input.lower() for word in ['low', 'sometime']):
            priority = 4
        
        # Extract basic timing
        deadline = None
        if 'tomorrow' in user_input.lower():
            deadline = timezone.now() + timedelta(days=1)
        elif 'next week' in user_input.lower():
            deadline = timezone.now() + timedelta(days=7)
        elif 'today' in user_input.lower():
            deadline = timezone.now() + timedelta(hours=8)
        
        return {
            'name': task_name or 'New Task',
            'description': '',
            'priority': priority,
            'status': 'pending',
            'deadline': deadline.isoformat() if deadline else None,
            'ai_suggested': True
        }

    def _generate_task_response(self, user_input: str, task_data: Dict) -> str:
        """Generate response for task creation"""
        task_name = task_data.get('name', 'your task')
        
        if self.llm.available:
            prompt = f"""You are Jarvis, a helpful AI assistant. The user said: "{user_input}"

You are creating a task called: "{task_name}"

Respond in a friendly, helpful way in 1-2 sentences. Confirm the task creation.

Response:"""
            
            ai_response = self.llm._call(prompt)
            if ai_response and ai_response.strip():
                return ai_response.strip()
        
        # Fallback response
        return f"I'll create the task '{task_name}' for you!"

    def _get_conversational_response(self, user_input: str) -> str:
        """Get conversational response - SIMPLIFIED"""
        
        if self.llm.available:
            prompt = f"""You are Jarvis, a helpful AI assistant for task management.

User said: "{user_input}"

Respond naturally in 1-2 sentences. Be helpful and friendly.

Response:"""
            
            ai_response = self.llm._call(prompt)
            if ai_response and ai_response.strip():
                return ai_response.strip()
        
        # Simple fallback responses
        user_lower = user_input.lower()
        
        if any(word in user_lower for word in ['hello', 'hi', 'hey']):
            return "Hello! I'm Jarvis, your task management assistant. How can I help you today?"
        
        elif any(word in user_lower for word in ['thank', 'thanks']):
            return "You're welcome! I'm always happy to help with your tasks."
        
        elif any(word in user_lower for word in ['help', 'what can you do']):
            return "I can help you create, manage, and organize your tasks. Just tell me what you need to do!"
        
        else:
            return "I understand! I'm here to help you stay organized and productive."

    def health_check(self) -> Dict[str, Any]:
        """Check agent health - FIXED"""
        try:
            if self.llm.available:
                # Test a simple generation
                test_response = self.llm._call("Hello", stop=None)
                
                return {
                    "status": "healthy",
                    "ollama_url": self.ollama_url,
                    "model": self.model,
                    "test_response": test_response[:50] if test_response else "No response"
                }
            else:
                return {
                    "status": "unhealthy",
                    "error": "Cannot connect to Ollama",
                    "ollama_url": self.ollama_url,
                    "model": self.model,
                    "fallback_available": True
                }
                
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "ollama_url": self.ollama_url,
                "model": self.model,
                "fallback_available": True
            }
    
    def process_conversation_context(self, conversation_history: List[str], new_input: str) -> Dict[str, Any]:
        """Process input with conversation context for better understanding"""
        
        context_prompt = PromptTemplate(
            template="""You are Jarvis, processing a conversation about task management with EDF/HPF scheduling focus.

CONVERSATION HISTORY:
{conversation_history}

NEW USER INPUT: {new_input}
CURRENT DATE/TIME: {current_datetime}

Consider the conversation context when understanding the user's request. They might be:
- Clarifying details about a previous request
- Adding to or modifying something they mentioned before
- Asking follow-up questions

Focus on extracting scheduling-relevant information:
- Duration in MINUTES
- Priority and urgency for HPF algorithm
- Deadlines for EDF algorithm
- Scheduling constraints

CRITICAL: Return ONLY valid JSON without any comments, explanations, or code block markers.

{format_instructions}

Return ONLY the JSON object:""",
            input_variables=["conversation_history", "new_input", "current_datetime"],
            partial_variables={"format_instructions": self.parser.get_format_instructions()}
        )
        
        context_chain = LLMChain(llm=self.llm, prompt=context_prompt)
        
        try:
            current_datetime = timezone.now().strftime("%Y-%m-%d %H:%M:%S %Z")
            history_text = "\n".join([f"- {msg}" for msg in conversation_history])
            
            response = context_chain.run(
                conversation_history=history_text,
                new_input=new_input,
                current_datetime=current_datetime
            )
            
            # Clean and parse response
            cleaned_response = clean_json_response(response)
            jarvis_response = self.parser.parse(cleaned_response)
            
            result = {
                "success": True,
                "should_create_task": jarvis_response.should_create_task,
                "ai_response": jarvis_response.conversational_response,
                "raw_response": response,
                "cleaned_response": cleaned_response,
                "user_input": new_input,
                "context_used": True
            }
            
            if jarvis_response.should_create_task and jarvis_response.task_data:
                result["task"] = jarvis_response.task_data.dict()
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Context processing error: {str(e)}",
                "ai_response": "I understand you're continuing our conversation, but I'm having trouble processing that right now. Could you help me understand what you need?",
                "user_input": new_input
            }
    
    def generate_schedule_suggestions(self, tasks: List[Dict], user_preferences: Dict = None) -> Dict[str, Any]:
        """Generate intelligent schedule suggestions using EDF/HPF algorithms"""
        
        schedule_prompt = PromptTemplate(
            template="""You are Jarvis, an intelligent scheduling assistant using EDF (Earliest Deadline First) and HPF (Highest Priority First) algorithms.

TASKS TO SCHEDULE:
{tasks_json}

USER PREFERENCES:
{user_preferences}

CURRENT DATE/TIME: {current_datetime}

Apply EDF/HPF scheduling principles:

EDF ALGORITHM:
1. Sort tasks by deadline (earliest first)
2. Consider deadline_flexibility_minutes for adjustments
3. Prioritize overdue tasks first
4. Account for task duration vs time until deadline

HPF ALGORITHM:
1. Sort tasks by calculated_priority (highest first)
2. Use base_priority * urgency_multiplier * deadline_factor
3. Consider category_weight from task categories
4. Balance high priority with feasibility

SCHEDULING CONSTRAINTS:
- Respect can_be_split and requires_consecutive_time
- Use estimated_duration_minutes for time allocation
- Consider preferred_time_of_day and avoid_time_of_day
- Account for required_energy_level and user's productive hours
- Ensure minimum_duration_minutes and maximum_duration_minutes

OPTIMIZATION GOALS:
1. Minimize deadline violations (EDF priority)
2. Maximize high-priority task completion (HPF priority)
3. Optimize time block utilization
4. Balance workload across time periods
5. Respect user preferences and constraints

Provide a detailed schedule with:
- EDF/HPF algorithm application rationale
- Specific time slots with justification
- Conflict resolution strategies
- Buffer time recommendations
- Priority vs deadline trade-off explanations

Output your schedule as a structured response with algorithm insights.""",
            input_variables=["tasks_json", "user_preferences", "current_datetime"]
        )
        
        schedule_chain = LLMChain(llm=self.llm, prompt=schedule_prompt)
        
        try:
            current_datetime = timezone.now().strftime("%Y-%m-%d %H:%M:%S %Z")
            
            response = schedule_chain.run(
                tasks_json=json.dumps(tasks, indent=2),
                user_preferences=json.dumps(user_preferences or {}, indent=2),
                current_datetime=current_datetime
            )
            
            return {
                "success": True,
                "schedule_suggestion": response,
                "tasks_count": len(tasks),
                "algorithm_used": "EDF/HPF Hybrid"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Schedule generation error: {str(e)}"
            }
    
    def health_check(self) -> Dict[str, Any]:
        """Check if Ollama is running and accessible"""
        try:
            if not self.ollama_url:
                return {
                    "status": "unhealthy",
                    "error": "No working Ollama URL found",
                    "ollama_url": "unknown",
                    "model": self.model
                }
            
            # Test connection
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            response.raise_for_status()
            
            # Test model availability
            test_response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": "Hello",
                    "stream": False
                },
                timeout=10
            )
            
            if test_response.status_code == 200:
                return {
                    "status": "healthy",
                    "ollama_url": self.ollama_url,
                    "model": self.model,
                    "available_models": self.available_models,
                    "optimization": "EDF/HPF Ready"
                }
            else:
                return {
                    "status": "unhealthy",
                    "error": f"Model {self.model} not available or not responding",
                    "ollama_url": self.ollama_url,
                    "model": self.model,
                    "available_models": self.available_models
                }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "ollama_url": self.ollama_url or "unknown",
                "model": self.model
            }


# ===================================
# DJANGO INTEGRATION FUNCTIONS
# ===================================

def create_jarvis_agent(ollama_url: str = "http://localhost:11434", model: str = None) -> JarvisTaskAgent:
    """Create a Jarvis agent - FIXED"""
    return JarvisTaskAgent(ollama_url=ollama_url, model=model)

def process_task_with_jarvis(user_input: str, user=None, agent: JarvisTaskAgent = None) -> Dict[str, Any]:
    """Process user input and create tasks - FIXED"""
    
    if not agent:
        agent = create_jarvis_agent()
    
    # Process the input
    result = agent.process_user_input(user_input, user)
    
    if not result["success"]:
        return result
    
    # If should create task and user is authenticated, create in database
    if user and result.get("should_create_task") and result.get("task"):
        try:
            # Get or create DeepTalk user
            deeptalk_user, created = DeepTalkUser.objects.get_or_create(
                user=user,
                defaults={'timezone': 'UTC', 'subscription_tier': 'free'}
            )
            
            task_data = result["task"]
            
            # Create task
            task = Task.objects.create(
                user=deeptalk_user,
                name=task_data["name"],
                description=task_data.get("description", ""),
                priority=task_data.get("priority", 3),
                status=task_data.get("status", "pending"),
                deadline=task_data.get("deadline"),
                ai_suggested=task_data.get("ai_suggested", True)
            )
            
            result["task_created"] = True
            result["task_id"] = str(task.id)
            
        except Exception as e:
            result["task_created"] = False
            result["db_error"] = str(e)
            logger.error(f"Database error creating task: {e}")
    else:
        result["task_created"] = False
    
    return result

def simple_task_processing(user_input, deeptalk_user):
    """Simple fallback task processing when AI is not available"""
    
    # Simple keyword detection
    task_keywords = ['task', 'todo', 'remind', 'schedule', 'need to', 'have to']
    should_create = any(keyword in user_input.lower() for keyword in task_keywords)
    
    if should_create and deeptalk_user:
        # Create a simple task
        try:
            task = Task.objects.create(
                user=deeptalk_user,
                name=user_input[:100],  # Limit name length
                description='',
                priority=3,
                status='pending',
                ai_suggested=False
            )
            
            return {
                "success": True,
                "should_create_task": True,
                "task_created": True,
                "ai_response": f"I've created a task: '{task.name}' for you!",
                "task": TaskSerializer(task).data
            }
        except Exception as e:
            logger.error(f"Simple task creation failed: {e}")
    
    return {
        "success": True,
        "should_create_task": should_create,
        "task_created": False,
        "ai_response": "I understand! Let me help you with that." if should_create else "I'm here to help with your tasks!"
    }

def create_time_blocks_from_preferences(user: DeepTalkUser) -> List[TimeBlock]:
    """Create default time blocks based on user preferences"""
    
    try:
        preferences = user.preferences
    except UserPreferences.DoesNotExist:
        # Create default preferences if none exist
        preferences = UserPreferences.objects.create(user=user)
    
    time_blocks = []
    
    # Create time blocks for the next 7 days
    start_date = timezone.now().date()
    for i in range(7):
        current_date = start_date + timedelta(days=i)
        
        # Skip weekends if not in preferred work days
        if preferences.preferred_work_days and current_date.weekday() not in preferences.preferred_work_days:
            continue
        
        # Create work time block
        work_start = timezone.make_aware(
            datetime.combine(current_date, preferences.work_start_time)
        )
        work_end = timezone.make_aware(
            datetime.combine(current_date, preferences.work_end_time)
        )
        
        # Create morning block (work start to lunch)
        lunch_start = work_start + timedelta(hours=4)  # Assume lunch after 4 hours
        morning_block = TimeBlock(
            user=user,
            start_time=work_start,
            end_time=lunch_start,
            block_type='available',
            status='available',
            can_be_split=True,
            min_task_duration_minutes=15,
            max_task_duration_minutes=240,  # 4 hours max
            flexibility_score=Decimal('1.0'),
            importance_weight=Decimal('1.0')
        )
        time_blocks.append(morning_block)
        
        # Create lunch break
        lunch_end = lunch_start + timedelta(minutes=preferences.lunch_break_duration)
        lunch_block = TimeBlock(
            user=user,
            start_time=lunch_start,
            end_time=lunch_end,
            block_type='break',
            status='occupied',
            can_be_split=False,
            flexibility_score=Decimal('0.3')  # Low flexibility for lunch
        )
        time_blocks.append(lunch_block)
        
        # Create afternoon block (lunch end to work end)
        afternoon_block = TimeBlock(
            user=user,
            start_time=lunch_end,
            end_time=work_end,
            block_type='available',
            status='available',
            can_be_split=True,
            min_task_duration_minutes=15,
            max_task_duration_minutes=240,
            flexibility_score=Decimal('1.0'),
            importance_weight=Decimal('1.0')
        )
        time_blocks.append(afternoon_block)
    
    return time_blocks


def run_edf_scheduling(user: DeepTalkUser, tasks: List[Task], time_blocks: List[TimeBlock]) -> Dict[str, Any]:
    """Run Earliest Deadline First scheduling algorithm"""
    from .models import SchedulingRun, ScheduleDecision
    import time as time_module
    
    start_time = time_module.time()
    
    # Create scheduling run record
    scheduling_run = SchedulingRun.objects.create(
        user=user,
        algorithm_used='EDF',
        algorithm_version='1.0',
        scheduling_window_start=min(block.start_time for block in time_blocks),
        scheduling_window_end=max(block.end_time for block in time_blocks),
        tasks_considered=len(tasks),
        time_blocks_available=len([b for b in time_blocks if b.status == 'available']),
        status='running'
    )
    
    try:
        # Sort tasks by deadline (EDF algorithm)
        tasks_with_deadline = [t for t in tasks if t.deadline]
        tasks_without_deadline = [t for t in tasks if not t.deadline]
        
        # EDF: Sort by deadline first, then by priority
        sorted_tasks = sorted(
            tasks_with_deadline, 
            key=lambda t: (t.deadline, -t.calculated_priority)
        ) + sorted(
            tasks_without_deadline,
            key=lambda t: -t.calculated_priority
        )
        
        # Available time blocks sorted by start time
        available_blocks = sorted(
            [b for b in time_blocks if b.status == 'available'],
            key=lambda b: b.start_time
        )
        
        scheduled_tasks = 0
        unscheduled_tasks = 0
        decisions = []
        
        # Schedule each task
        for task in sorted_tasks:
            scheduled = False
            
            # Find suitable time block
            for block in available_blocks:
                # Check if task fits in this block
                if (block.duration_minutes >= task.estimated_duration_minutes and
                    (not block.min_task_duration_minutes or task.estimated_duration_minutes >= block.min_task_duration_minutes) and
                    (not block.max_task_duration_minutes or task.estimated_duration_minutes <= block.max_task_duration_minutes)):
                    
                    # Calculate scheduling scores
                    deadline_urgency = 0.0
                    if task.deadline:
                        time_until_deadline = (task.deadline - block.start_time).total_seconds() / 3600  # hours
                        deadline_urgency = max(0, 100 - time_until_deadline)  # Higher score for closer deadlines
                    
                    # Create schedule decision
                    decision = ScheduleDecision.objects.create(
                        scheduling_run=scheduling_run,
                        task=task,
                        time_block=block,
                        scheduled_start_time=block.start_time,
                        scheduled_end_time=block.start_time + timedelta(minutes=task.estimated_duration_minutes),
                        decision_reason=f"EDF: Task deadline {task.deadline}, fits in block {block.start_time}",
                        priority_score=Decimal(str(task.calculated_priority)),
                        deadline_urgency_score=Decimal(str(deadline_urgency)),
                        efficiency_score=Decimal(str(task.estimated_duration_minutes / block.duration_minutes * 100)),
                        is_optimal=True,
                        confidence_level=Decimal('0.8')
                    )
                    decisions.append(decision)
                    
                    # Update block availability
                    if task.estimated_duration_minutes >= block.duration_minutes:
                        # Task takes entire block
                        block.status = 'occupied'
                        available_blocks.remove(block)
                    else:
                        # Split block if task allows it and block allows it
                        if task.can_be_split and block.can_be_split:
                            # Create remaining block
                            remaining_start = block.start_time + timedelta(minutes=task.estimated_duration_minutes)
                            if remaining_start < block.end_time:
                                # Update original block end time
                                block.end_time = remaining_start
                                # Note: In real implementation, you'd create a new TimeBlock for the remainder
                    
                    scheduled_tasks += 1
                    scheduled = True
                    break
            
            if not scheduled:
                unscheduled_tasks += 1
        
        # Calculate performance metrics
        execution_time = int((time_module.time() - start_time) * 1000)  # milliseconds
        deadline_violations = sum(1 for task in sorted_tasks 
                                if task.deadline and task.deadline < timezone.now())
        
        # Update scheduling run with results
        scheduling_run.tasks_scheduled = scheduled_tasks
        scheduling_run.tasks_unscheduled = unscheduled_tasks
        scheduling_run.execution_time_ms = execution_time
        scheduling_run.deadline_violations = deadline_violations
        scheduling_run.schedule_efficiency_score = Decimal(str(scheduled_tasks / len(tasks) * 100)) if tasks else Decimal('0')
        scheduling_run.deadline_compliance_rate = Decimal(str((len(tasks) - deadline_violations) / len(tasks) * 100)) if tasks else Decimal('100')
        scheduling_run.status = 'completed'
        scheduling_run.save()
        
        return {
            "success": True,
            "algorithm": "EDF",
            "scheduling_run_id": str(scheduling_run.id),
            "tasks_scheduled": scheduled_tasks,
            "tasks_unscheduled": unscheduled_tasks,
            "execution_time_ms": execution_time,
            "deadline_violations": deadline_violations,
            "efficiency_score": float(scheduling_run.schedule_efficiency_score),
            "decisions": [
                {
                    "task_id": str(d.task.id),
                    "task_name": d.task.name,
                    "scheduled_start": d.scheduled_start_time.isoformat() if d.scheduled_start_time else None,
                    "scheduled_end": d.scheduled_end_time.isoformat() if d.scheduled_end_time else None,
                    "priority_score": float(d.priority_score),
                    "deadline_urgency": float(d.deadline_urgency_score)
                } for d in decisions
            ]
        }
        
    except Exception as e:
        scheduling_run.status = 'failed'
        scheduling_run.error_message = str(e)
        scheduling_run.save()
        
        return {
            "success": False,
            "error": f"EDF scheduling failed: {str(e)}",
            "scheduling_run_id": str(scheduling_run.id)
        }


def run_hpf_scheduling(user: DeepTalkUser, tasks: List[Task], time_blocks: List[TimeBlock]) -> Dict[str, Any]:
    """Run Highest Priority First scheduling algorithm"""
    from .models import SchedulingRun, ScheduleDecision
    import time as time_module
    
    start_time = time_module.time()
    
    # Create scheduling run record
    scheduling_run = SchedulingRun.objects.create(
        user=user,
        algorithm_used='HPF',
        algorithm_version='1.0',
        scheduling_window_start=min(block.start_time for block in time_blocks),
        scheduling_window_end=max(block.end_time for block in time_blocks),
        tasks_considered=len(tasks),
        time_blocks_available=len([b for b in time_blocks if b.status == 'available']),
        status='running'
    )
    
    try:
        # Sort tasks by calculated priority (HPF algorithm)
        sorted_tasks = sorted(tasks, key=lambda t: -t.calculated_priority)  # Highest priority first
        
        # Available time blocks sorted by start time
        available_blocks = sorted(
            [b for b in time_blocks if b.status == 'available'],
            key=lambda b: b.start_time
        )
        
        scheduled_tasks = 0
        unscheduled_tasks = 0
        decisions = []
        total_priority_score = 0
        
        # Schedule each task
        for task in sorted_tasks:
            scheduled = False
            best_block = None
            best_score = -1
            
            # Find best suitable time block
            for block in available_blocks:
                # Check if task fits in this block
                if (block.duration_minutes >= task.estimated_duration_minutes and
                    (not block.min_task_duration_minutes or task.estimated_duration_minutes >= block.min_task_duration_minutes) and
                    (not block.max_task_duration_minutes or task.estimated_duration_minutes <= block.max_task_duration_minutes)):
                    
                    # Calculate block suitability score
                    efficiency = task.estimated_duration_minutes / block.duration_minutes
                    timing_score = 1.0  # Could be enhanced with preferred times
                    
                    # Combine scores
                    block_score = (
                        float(task.calculated_priority) * 0.4 +  # Priority weight
                        efficiency * 0.3 +  # Efficiency weight
                        timing_score * 0.2 +  # Timing weight
                        float(block.importance_weight) * 0.1  # Block importance
                    )
                    
                    if block_score > best_score:
                        best_score = block_score
                        best_block = block
            
            if best_block:
                # Schedule task in best block
                decision = ScheduleDecision.objects.create(
                    scheduling_run=scheduling_run,
                    task=task,
                    time_block=best_block,
                    scheduled_start_time=best_block.start_time,
                    scheduled_end_time=best_block.start_time + timedelta(minutes=task.estimated_duration_minutes),
                    decision_reason=f"HPF: Highest priority task ({task.calculated_priority}) scheduled in optimal block",
                    priority_score=Decimal(str(task.calculated_priority)),
                    efficiency_score=Decimal(str(best_score)),
                    is_optimal=True,
                    confidence_level=Decimal('0.85')
                )
                decisions.append(decision)
                
                # Update block availability
                if task.estimated_duration_minutes >= best_block.duration_minutes:
                    best_block.status = 'occupied'
                    available_blocks.remove(best_block)
                
                scheduled_tasks += 1
                total_priority_score += task.calculated_priority
                scheduled = True
            
            if not scheduled:
                unscheduled_tasks += 1
        
        # Calculate performance metrics
        execution_time = int((time_module.time() - start_time) * 1000)  # milliseconds
        average_priority = total_priority_score / scheduled_tasks if scheduled_tasks > 0 else 0
        
        # Update scheduling run with results
        scheduling_run.tasks_scheduled = scheduled_tasks
        scheduling_run.tasks_unscheduled = unscheduled_tasks
        scheduling_run.execution_time_ms = execution_time
        scheduling_run.average_priority_score = Decimal(str(average_priority))
        scheduling_run.schedule_efficiency_score = Decimal(str(scheduled_tasks / len(tasks) * 100)) if tasks else Decimal('0')
        scheduling_run.status = 'completed'
        scheduling_run.save()
        
        return {
            "success": True,
            "algorithm": "HPF",
            "scheduling_run_id": str(scheduling_run.id),
            "tasks_scheduled": scheduled_tasks,
            "tasks_unscheduled": unscheduled_tasks,
            "execution_time_ms": execution_time,
            "average_priority_score": average_priority,
            "efficiency_score": float(scheduling_run.schedule_efficiency_score),
            "decisions": [
                {
                    "task_id": str(d.task.id),
                    "task_name": d.task.name,
                    "scheduled_start": d.scheduled_start_time.isoformat() if d.scheduled_start_time else None,
                    "scheduled_end": d.scheduled_end_time.isoformat() if d.scheduled_end_time else None,
                    "priority_score": float(d.priority_score),
                    "efficiency_score": float(d.efficiency_score)
                } for d in decisions
            ]
        }
        
    except Exception as e:
        scheduling_run.status = 'failed'
        scheduling_run.error_message = str(e)
        scheduling_run.save()
        
        return {
            "success": False,
            "error": f"HPF scheduling failed: {str(e)}",
            "scheduling_run_id": str(scheduling_run.id)
        }