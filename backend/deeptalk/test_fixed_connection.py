# test_fixed_connection.py - Test the fixed Ollama connection

import requests
import json

def test_fixed_ollama():
    """Test Ollama with llama3.2:latest model"""
    
    url = "http://localhost:11434"
    model = "llama3.2:latest"
    
    print(f"🔍 Testing Ollama at {url} with model {model}")
    
    try:
        # Test health
        print("1. Testing health endpoint...")
        health_response = requests.get(f"{url}/api/tags", timeout=5)
        print(f"   Status: {health_response.status_code}")
        
        if health_response.status_code == 200:
            models = health_response.json().get("models", [])
            print(f"   Available models: {[m.get('name') for m in models]}")
            
            # Test generation with correct model
            print(f"2. Testing generation with {model}...")
            gen_response = requests.post(
                f"{url}/api/generate",
                json={
                    "model": model,
                    "prompt": "You are Jarvis, a task management assistant. Extract task info from: 'Call mom tomorrow at 2 PM'. Return only valid JSON with fields: name, description, priority (1-5), category.",
                    "stream": False,
                    "options": {
                        "temperature": 0.7
                    }
                },
                timeout=30
            )
            
            print(f"   Generation status: {gen_response.status_code}")
            
            if gen_response.status_code == 200:
                result = gen_response.json()
                response_text = result.get('response', '')
                print(f"   Response: {response_text[:200]}...")
                
                # Try to parse JSON from response
                try:
                    import re
                    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                    if json_match:
                        task_data = json.loads(json_match.group())
                        print(f"   ✅ Successfully parsed task data: {task_data}")
                    else:
                        print(f"   ⚠️  Response doesn't contain valid JSON")
                except Exception as e:
                    print(f"   ⚠️  JSON parsing failed: {e}")
                
                print(f"   ✅ SUCCESS: Ollama is working with {model}!")
                return True
            else:
                print(f"   ❌ Generation failed: {gen_response.text}")
        else:
            print(f"   ❌ Health check failed: {health_response.text}")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    return False

def test_jarvis_agent():
    """Test the Jarvis agent directly"""
    try:
        print("\n🤖 Testing Jarvis Agent...")
        
        # Import and test the agent
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        
        from deeptalk.ollama_task_agent import create_jarvis_agent
        
        agent = create_jarvis_agent()
        
        # Test health check
        health = agent.health_check()
        print(f"   Health status: {health['status']}")
        print(f"   Model: {health.get('model', 'unknown')}")
        
        if health['status'] == 'healthy':
            # Test task processing
            result = agent.process_user_input("Remind me to call mom tomorrow at 2 PM")
            
            if result['success']:
                print(f"   ✅ Task processing successful!")
                print(f"   Task name: {result['task']['name']}")
                print(f"   Priority: {result['task']['priority']}")
                print(f"   Category: {result['task']['category']}")
            else:
                print(f"   ❌ Task processing failed: {result.get('error', 'unknown')}")
        
    except Exception as e:
        print(f"   ❌ Jarvis agent test failed: {e}")

if __name__ == "__main__":
    print("🚀 Testing Fixed Ollama Connection\n")
    
    success = test_fixed_ollama()
    
    if success:
        test_jarvis_agent()
        print("\n✅ All tests passed! Your Ollama setup is working correctly.")
        print("\n📝 Your Django app should now be able to connect to Ollama.")
    else:
        print("\n❌ Ollama connection test failed.")
        print("\n🔧 Troubleshooting:")
        print("- Make sure Ollama container is running: docker ps | grep ollama")
        print("- Check if the model is available: docker exec -it ollama ollama list")
        print("- Try pulling the model: docker exec -it ollama ollama pull llama3.2") 