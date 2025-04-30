"""Main monitoring agent script."""
import time
import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS

# Import local modules
import config
import agent_id
import collectors

def main():
    """Main entry point for the monitoring agent."""
    # Initialize collectors
    collectors.initialize()
    
    # Get the agent ID
    host = agent_id.get_agent_id()
    print(f"Using agent ID: {host}")
    
    # Initialize InfluxDB client
    client = influxdb_client.InfluxDBClient(
        url=config.INFLUXDB_URL, 
        token=config.INFLUXDB_TOKEN, 
        org=config.INFLUXDB_ORG
    )
    write_api = client.write_api(write_options=SYNCHRONOUS)
    
    # Main collection loop
    while True:
        try:
            # Collect all metrics
            metrics = collectors.collect_all(host)
            
            # Send metrics to InfluxDB
            write_api.write(bucket=config.INFLUXDB_BUCKET, org=config.INFLUXDB_ORG, record=metrics)
            print("Metrics written successfully.")
        except Exception as e:
            print(f"Error sending data to InfluxDB: {e}")
        
        # Wait for next collection cycle
        time.sleep(config.COLLECTION_INTERVAL)

if __name__ == "__main__":
    main()
