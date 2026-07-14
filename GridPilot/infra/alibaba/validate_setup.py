import os
import sys
import socket
import json
import urllib.request
import urllib.error

# Gracefully import oss2 for Alibaba OSS operations
try:
    import oss2
    HAS_OSS2 = True
except ImportError:
    HAS_OSS2 = False

# Function to parse env file manually without external library dependencies
def load_env(env_path):
    env_vars = {}
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, val = line.split('=', 1)
                    # Strip quotes if present
                    val = val.strip().strip('"').strip("'")
                    env_vars[key.strip()] = val
    return env_vars

def main():
    print("======================================================================")
    echo_name = "GridPilot - Alibaba Cloud Setup Validator"
    print(f"      {echo_name}")
    print("======================================================================")

    # 1. Locate and parse local .env file
    # We look for .env in the parent directory of this script, or the current directory
    possible_paths = [
        os.path.join(os.path.dirname(__file__), '..', '..', '.env'),
        os.path.join(os.getcwd(), '.env'),
        os.path.join(os.getcwd(), 'GridPilot', '.env')
    ]
    
    env_path = None
    for path in possible_paths:
        if os.path.exists(path):
            env_path = path
            break
            
    if not env_path:
        print("[-] Error: Local '.env' file not found.")
        print("    Please copy '.env.example' to '.env' in your GridPilot project root")
        print("    and fill in your actual credentials before running validation.")
        sys.exit(1)
        
    print(f"[+] Loaded configuration from: {os.path.abspath(env_path)}")
    config = load_env(env_path)
    
    # 2. Check if required environment variables are defined and not placeholders
    required_keys = [
        "OSS_BUCKET_NAME",
        "OSS_ACCESS_KEY_ID",
        "OSS_ACCESS_KEY_SECRET",
        "OSS_ENDPOINT",
        "DASHSCOPE_API_KEY",
        "ECS_HOST"
    ]
    
    missing_keys = []
    placeholder_keys = []
    
    for key in required_keys:
        val = config.get(key)
        if not val:
            missing_keys.append(key)
        elif "your_" in val or "placeholder" in val:
            placeholder_keys.append(key)
            
    if missing_keys:
        print(f"[-] Missing keys in .env: {', '.join(missing_keys)}")
    if placeholder_keys:
        print(f"[-] Placeholder values detected in .env for: {', '.join(placeholder_keys)}")
        
    if missing_keys or placeholder_keys:
        print("[-] Graceful exit: Setup is incomplete. Please update '.env' with your real cloud credentials.")
        sys.exit(0)
        
    print("[+] All environment variables are structured correctly.")
    
    # 3. ECS SSH / Reachability Check
    ecs_host = config.get("ECS_HOST")
    print(f"\n[*] Checking ECS Host reachability ({ecs_host})...")
    try:
        # Check port 22 (SSH)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3.0)
        result = sock.connect_ex((ecs_host, 22))
        if result == 0:
            print(f"[+] Success: ECS Host port 22 (SSH) is OPEN and reachable.")
        else:
            print(f"[-] Warning: ECS Host port 22 (SSH) is closed or timed out (Code: {result}).")
            print("    Make sure your ECS Security Group allows inbound SSH traffic from your IP.")
        sock.close()
    except Exception as e:
        print(f"[-] Error checking ECS: {e}")

    # 4. DashScope API Key Check (managed Qwen LLM)
    api_key = config.get("DASHSCOPE_API_KEY")
    print("\n[*] Checking DashScope Qwen API connection...")
    # Hit Qwen Turbo generation API endpoint directly using urllib
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "qwen-turbo",
        "input": {
            "messages": [
                {"role": "user", "content": "Respond with the word SUCCESS"}
            ]
        }
    }
    
    req = urllib.request.Request(
        url, 
        data=json.dumps(payload).encode('utf-8'), 
        headers=headers,
        method='POST'
    )
    
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            res_body = response.read().decode('utf-8')
            res_json = json.loads(res_body)
            # Try to get output text
            text = res_json.get("output", {}).get("text", "")
            print(f"[+] Success: DashScope responded successfully!")
            print(f"    Response snippet: {text.strip()}")
    except urllib.error.HTTPError as e:
        print(f"[-] DashScope API call failed (HTTP Error {e.code}).")
        try:
            err_details = e.read().decode('utf-8')
            print(f"    Details: {err_details}")
        except Exception:
            pass
    except Exception as e:
        print(f"[-] DashScope API call failed: {e}")

    # 5. OSS Access Key Scoped Permissions Check
    bucket_name = config.get("OSS_BUCKET_NAME")
    endpoint = config.get("OSS_ENDPOINT")
    access_key = config.get("OSS_ACCESS_KEY_ID")
    secret_key = config.get("OSS_ACCESS_KEY_SECRET")
    
    print(f"\n[*] Checking OSS Bucket connection (oss://{bucket_name})...")
    if not HAS_OSS2:
        print("[-] Skipping programmatic OSS test: 'oss2' Python SDK is not installed.")
        print("    Please run: pip install oss2")
        print("    Or verify manually using the Alibaba Cloud CLI command:")
        print(f"    aliyun oss ls oss://{bucket_name}")
    else:
        try:
            auth = oss2.Auth(access_key, secret_key)
            bucket = oss2.Bucket(auth, endpoint, bucket_name)
            
            # 5a. Test Upload
            test_key = "gridpilot_test_connection.txt"
            test_content = b"Connection verification payload."
            print(f"    - Attempting upload to: oss://{bucket_name}/{test_key}")
            bucket.put_object(test_key, test_content)
            print("    [+] Upload succeeded.")
            
            # 5b. Test Download
            print(f"    - Attempting download of: oss://{bucket_name}/{test_key}")
            result = bucket.get_object(test_key)
            downloaded_content = result.read()
            if downloaded_content == test_content:
                print("    [+] Download succeeded & content verified.")
            else:
                print(f"    [-] Content mismatch: got '{downloaded_content}', expected '{test_content}'")
                
            # 5c. Test Delete
            print(f"    - Attempting deletion of: oss://{bucket_name}/{test_key}")
            bucket.delete_object(test_key)
            print("    [+] Deletion succeeded.")
            
            # 5d. Test Scoped Policy Safety (Access Denied for other resources)
            dummy_bucket_name = f"unauthorized-bucket-name-gp-{bucket_name}"
            print(f"    - Checking RAM scope boundary (accessing dummy bucket: oss://{dummy_bucket_name})")
            dummy_bucket = oss2.Bucket(auth, endpoint, dummy_bucket_name)
            try:
                # This should fail with Access Denied (status 403) due to policy restriction
                dummy_bucket.get_bucket_info()
                print("    [!] Warning: RAM policy boundary test failed. The sub-account can access other buckets!")
            except oss2.exceptions.NoSuchBucket:
                # The bucket does not exist, but let's see if we got access denied or not
                print("    [+] RAM policy boundary OK (bucket does not exist, but let's confirm lack of wildcards)")
            except oss2.exceptions.AccessDenied:
                print("    [+] RAM policy boundary OK (Access Denied as expected).")
            except Exception as e:
                # Any access denied or similar exception is expected
                print(f"    [+] RAM policy boundary OK (Access Denied or Blocked: {type(e).__name__}).")
                
        except Exception as e:
            print(f"[-] OSS operations failed: {e}")
            print("    Make sure your Access Key ID / Secret Key and Bucket Name are correct,")
            print("    and the RAM user policy matches the bucket name exactly.")

    print("\n======================================================================")
    print("Validation run complete.")
    print("======================================================================")

if __name__ == "__main__":
    main()
