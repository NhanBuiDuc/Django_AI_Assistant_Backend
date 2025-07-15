import os
import json
import base64
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from langchain.llms import OpenAI
from langchain.chat_models import ChatOpenAI
from langchain.schema import BaseMessage, HumanMessage, SystemMessage
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain.chains import LLMChain
from langchain.memory import ConversationBufferMemory
from langchain.agents import Tool, AgentExecutor, create_react_agent
from langchain.tools import BaseTool
from langchain.callbacks.manager import CallbackManagerForToolRun
from googleapiclient.discovery import build
from django.conf import settings
from .models import GoogleToken
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

def get_gmail_service(user):
    """Get Gmail service for authenticated user"""
    try:
        google_token = GoogleToken.objects.get(user=user)
        
        credentials = Credentials(
            token=google_token.access_token,
            refresh_token=google_token.refresh_token,
            token_uri=google_token.token_uri,
            client_id=google_token.client_id,
            client_secret=google_token.client_secret,
            scopes=google_token.scopes
        )
        
        # Refresh token if needed
        if credentials.expired:
            credentials.refresh(Request())
            google_token.access_token = credentials.token
            google_token.save()
        
        return build('gmail', 'v1', credentials=credentials)
        
    except GoogleToken.DoesNotExist:
        return None

class EmailSummarizerAgent:
    """AI Agent for summarizing Gmail emails using LangChain and OpenAI"""
    
    def __init__(self, openai_api_key: str, user):
        self.user = user
        self.llm = ChatOpenAI(
            openai_api_key=openai_api_key,
            model_name="gpt-3.5-turbo",  # or "gpt-4" for better results
            temperature=0.3
        )
        self.gmail_service = get_gmail_service(user)
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )
        
        # Create tools for the agent
        self.tools = self._create_tools()
        
    def _create_tools(self) -> List[Tool]:
        """Create tools that the agent can use"""
        
        def get_recent_emails(query: str = "") -> str:
            """Get recent emails from Gmail"""
            try:
                # Get recent emails
                kwargs = {'userId': 'me', 'maxResults': 20}
                if query:
                    kwargs['q'] = query
                    
                results = self.gmail_service.users().messages().list(**kwargs).execute()
                messages = results.get('messages', [])
                
                emails_data = []
                for message in messages[:10]:  # Limit to 10 for efficiency
                    try:
                        msg = self.gmail_service.users().messages().get(
                            userId='me',
                            id=message['id']
                        ).execute()
                        
                        headers = msg['payload'].get('headers', [])
                        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
                        from_email = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
                        date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')
                        
                        # Get message body
                        body = self._extract_message_body(msg)
                        
                        emails_data.append({
                            'subject': subject,
                            'from': from_email,
                            'date': date,
                            'body': body[:500],  # Limit body length
                            'snippet': msg.get('snippet', '')
                        })
                    except Exception as e:
                        continue
                
                return json.dumps(emails_data, indent=2)
            except Exception as e:
                return f"Error fetching emails: {str(e)}"
        
        def search_emails(query: str) -> str:
            """Search emails by query"""
            try:
                results = self.gmail_service.users().messages().list(
                    userId='me',
                    q=query,
                    maxResults=10
                ).execute()
                
                messages = results.get('messages', [])
                
                emails_data = []
                for message in messages:
                    try:
                        msg = self.gmail_service.users().messages().get(
                            userId='me',
                            id=message['id']
                        ).execute()
                        
                        headers = msg['payload'].get('headers', [])
                        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
                        from_email = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
                        date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')
                        
                        emails_data.append({
                            'subject': subject,
                            'from': from_email,
                            'date': date,
                            'snippet': msg.get('snippet', '')
                        })
                    except Exception as e:
                        continue
                
                return json.dumps(emails_data, indent=2)
            except Exception as e:
                return f"Error searching emails: {str(e)}"
        
        def get_email_stats() -> str:
            """Get email statistics"""
            try:
                profile = self.gmail_service.users().getProfile(userId='me').execute()
                return json.dumps({
                    'total_messages': profile['messagesTotal'],
                    'total_threads': profile['threadsTotal'],
                    'email_address': profile['emailAddress']
                })
            except Exception as e:
                return f"Error getting stats: {str(e)}"
        
        return [
            Tool(
                name="get_recent_emails",
                description="Get recent emails from Gmail. Can optionally filter with a query.",
                func=get_recent_emails
            ),
            Tool(
                name="search_emails",
                description="Search emails by query (e.g., 'from:example@gmail.com', 'subject:meeting', 'is:unread')",
                func=search_emails
            ),
            Tool(
                name="get_email_stats",
                description="Get email account statistics including total messages and threads",
                func=get_email_stats
            )
        ]
    
    def _extract_message_body(self, message):
        """Extract text body from Gmail message"""
        body = ""
        
        if 'parts' in message['payload']:
            for part in message['payload']['parts']:
                if part['mimeType'] == 'text/plain' and 'data' in part['body']:
                    body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                    break
                elif part['mimeType'] == 'text/html' and 'data' in part['body']:
                    body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
        else:
            if (message['payload']['mimeType'] == 'text/plain' and 
                'data' in message['payload']['body']):
                body = base64.urlsafe_b64decode(
                    message['payload']['body']['data']
                ).decode('utf-8')
        
        return body
    
    def summarize_emails(self, query: str = "", num_emails: int = 10) -> str:
        """Summarize emails based on query"""
        
        # Create a summarization prompt
        system_template = """You are an AI assistant that helps users understand their emails. 
        You will receive email data and should provide clear, concise summaries.
        
        Guidelines:
        - Focus on important information and action items
        - Group similar emails together
        - Highlight urgent or important messages
        - Provide a brief overview followed by details
        - Be conversational and helpful
        """
        
        human_template = """Please analyze and summarize these emails:
        
        Query: {query}
        Number of emails: {num_emails}
        
        Email Data:
        {email_data}
        
        Please provide:
        1. A brief overview of the emails
        2. Key highlights and important messages
        3. Any action items or urgent matters
        4. A summary organized by topic or sender if relevant
        """
        
        # Get emails
        if query:
            email_data = self.tools[1].func(query)  # search_emails
        else:
            email_data = self.tools[0].func()  # get_recent_emails
        
        # Create the prompt
        system_message = SystemMessage(content=system_template)
        human_message = HumanMessage(
            content=human_template.format(
                query=query or "Recent emails",
                num_emails=num_emails,
                email_data=email_data
            )
        )
        
        # Get AI response
        response = self.llm([system_message, human_message])
        
        return response.content
    
    def analyze_specific_email(self, email_id: str) -> str:
        """Analyze a specific email in detail"""
        try:
            msg = self.gmail_service.users().messages().get(
                userId='me',
                id=email_id,
                format='full'
            ).execute()
            
            headers = msg['payload'].get('headers', [])
            message_headers = {}
            for header in headers:
                message_headers[header['name']] = header['value']
            
            body = self._extract_message_body(msg)
            
            email_data = {
                'headers': message_headers,
                'body': body,
                'snippet': msg.get('snippet', ''),
                'labels': msg.get('labelIds', [])
            }
            
            system_template = """You are an AI assistant that analyzes individual emails in detail.
            Provide insights about the email content, intent, and any action items."""
            
            human_template = """Please analyze this email in detail:
            
            Email Data:
            {email_data}
            
            Please provide:
            1. Summary of the email content
            2. Sender's intent or purpose
            3. Any action items or deadlines
            4. Importance level (High/Medium/Low)
            5. Suggested response or next steps
            """
            
            system_message = SystemMessage(content=system_template)
            human_message = HumanMessage(
                content=human_template.format(email_data=json.dumps(email_data, indent=2))
            )
            
            response = self.llm([system_message, human_message])
            return response.content
            
        except Exception as e:
            return f"Error analyzing email: {str(e)}"
    
    def get_daily_summary(self) -> str:
        """Get a daily summary of emails"""
        today = datetime.now().strftime('%Y/%m/%d')
        query = f"after:{today}"
        
        return self.summarize_emails(query=query)
    
    def get_unread_summary(self) -> str:
        """Get summary of unread emails"""
        return self.summarize_emails(query="is:unread")
    
    def get_important_summary(self) -> str:
        """Get summary of important emails"""
        return self.summarize_emails(query="is:important OR is:starred")


# ===================================
# DJANGO VIEWS FOR AI AGENT
# ===================================

# def create_ai_agent(user, openai_api_key: str = None) -> EmailSummarizerAgent:
#     """Create an AI agent for the user"""
#     if not openai_api_key:
#         openai_api_key = getattr(settings, 'OPENAI_API_KEY', None)
#         if not openai_api_key:
#             raise ValueError("OpenAI API key is required")
    
#     return EmailSummarizerAgent(openai_api_key, user)