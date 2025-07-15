# test_ollama_connection.py - Run this script to test Ollama connection

import requests
import json

def test_ollama_connection():
    """Test different ways to connect to Ollama"""
    
    # Possible URLs to try
    urls = [
        "http://localhost:11434",
        "http://127.0.0.1:11434",
        "http://host.docker.internal:11434",
        "http://172.18.0.2:11434",  # Your container IP
    ]
    
    for url in urls:
        print(f"\n=== Testing {url} ===")
        
        try:
            # Test /api/tags endpoint
            print("1. Testing /api/tags...")
            response = requests.get(f"{url}/api/tags", timeout=5)
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                models = response.json().get("models", [])
                print(f"   Available models: {len(models)}")
                for model in models:
                    print(f"     - {model.get('name', 'Unknown')}")
                
                # Test generation
                print("2. Testing generation...")
                gen_response = requests.post(
                    f"{url}/api/generate",
                    json={
                        "model": "llama3.1",
                        "prompt": "Hello, respond with just 'Hi there!'",
                        "stream": False
                    },
                    timeout=30
                )
                print(f"   Generation status: {gen_response.status_code}")
                
                if gen_response.status_code == 200:
                    result = gen_response.json()
                    print(f"   Response: {result.get('response', 'No response')}")
                    print(f"   ✅ SUCCESS: {url} is working!")
                    return url
                else:
                    print(f"   ❌ Generation failed: {gen_response.text}")
            else:
                print(f"   ❌ Tags endpoint failed: {response.text}")
                
        except requests.exceptions.ConnectionError:
            print(f"   ❌ Connection failed: Cannot connect to {url}")
        except requests.exceptions.Timeout:
            print(f"   ❌ Timeout: Request to {url} timed out")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    print("\n❌ No working Ollama URL found")
    return None

def pull_model_if_needed(url, model_name="llama3.1"):
    """Pull the model if it's not available"""
    try:
        print(f"\n=== Checking if {model_name} is available ===")
        response = requests.get(f"{url}/api/tags", timeout=5)
        
        if response.status_code == 200:
            models = response.json().get("models", [])
            model_names = [m.get("name", "") for m in models]
            
            if any(model_name in name for name in model_names):
                print(f"✅ {model_name} is already available")
                return True
            else:
                print(f"❌ {model_name} not found. Available models: {model_names}")
                print(f"To install {model_name}, run: docker exec -it ollama ollama pull {model_name}")
                return False
        
    except Exception as e:
        print(f"Error checking models: {e}")
        return False

if __name__ == "__main__":
    print("🔍 Testing Ollama connections...")
    
    working_url = test_ollama_connection()
    
    if working_url:
        print(f"\n🎉 Found working Ollama at: {working_url}")
        pull_model_if_needed(working_url)
        
        print(f"\n📝 Update your Django settings:")
        print(f"OLLAMA_BASE_URL = '{working_url}'")
        
    else:
        print("\n🚨 Troubleshooting steps:")
        print("1. Make sure Ollama container is running:")
        print("   docker ps | grep ollama")
        print("\n2. Check if port 11434 is exposed:")
        print("   docker port <container_name>")
        print("\n3. Try pulling a model:")
        print("   docker exec -it ollama ollama pull llama3.1")
        print("\n4. Check container logs:")
        print("   docker logs ollama")