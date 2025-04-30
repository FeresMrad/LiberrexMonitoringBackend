"""Agent ID management functions."""
import os
import uuid
from config import AGENT_ID_FILE

def get_agent_id():
    """Get or generate the agent ID.
    
    Returns:
        str: The agent ID from file or a newly generated UUID
    """
    # First check if the ID file exists
    if os.path.exists(AGENT_ID_FILE):
        try:
            with open(AGENT_ID_FILE, 'r') as f:
                agent_id = f.read().strip()
                if agent_id:
                    return agent_id
        except Exception as e:
            print(f"Error reading agent ID file: {e}")
    
    # If we got here, either the file doesn't exist or is empty/corrupted
    # Generate a new agent ID
    agent_id = str(uuid.uuid4())
    
    # Try to save it to the file
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(AGENT_ID_FILE), exist_ok=True)
        
        with open(AGENT_ID_FILE, 'w') as f:
            f.write(agent_id)
    except Exception as e:
        print(f"Error saving agent ID file: {e}")
    
    return agent_id
