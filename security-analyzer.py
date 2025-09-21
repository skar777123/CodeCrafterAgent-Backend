import subprocess
import json
import os
import logging
from flask import Flask, request, jsonify

# Configure basic logging for visibility in a production environment
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize the Flask application
app = Flask(__name__)

@app.route('/analyze', methods=['POST'])
def analyze_security():
    """
    A production-ready Flask API endpoint to analyze Solidity code using Slither.
    It expects a POST request with a JSON payload containing a "code" key.
    """
    logging.info("Received request on /analyze endpoint.")
    
    # 1. Input Validation
    try:
        request_json = request.get_json()
        if not request_json or 'code' not in request_json:
            logging.warning("Invalid request: Missing JSON payload or 'code' key.")
            return jsonify({"error": "Invalid request. JSON payload with 'code' key is required."}), 400

        solidity_code = request_json['code']
        if not isinstance(solidity_code, str) or not solidity_code.strip():
            logging.warning("Invalid request: 'code' field is empty or not a string.")
            return jsonify({"error": "The 'code' field must be a non-empty string."}), 400
    except Exception:
        logging.error("Failed to parse request JSON.")
        return jsonify({"error": "Could not parse request body as JSON."}), 400

    # 2. Stateless File Handling
    # Use a temporary file path that is safe for stateless/containerized environments.
    file_path = "/tmp/Contract.sol"

    try:
        with open(file_path, "w") as f:
            f.write(solidity_code)
        
        # 3. Secure Subprocess Execution
        # Define the Slither command. The '--json -' flag outputs JSON to stdout.
        command = ["slither", file_path, "--json", "-"]
        logging.info(f"Executing Slither command for request.")
        
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60  # Add a timeout to prevent long-running processes
        )

        # Slither often exits with a non-zero code if issues are found, 
        # but can also fail to produce output on a critical error (e.g., compile failure).
        if result.returncode != 0 and not result.stdout:
             raise subprocess.CalledProcessError(result.returncode, command, stderr=result.stderr)
        
        analysis_report = json.loads(result.stdout)
        logging.info("Slither analysis successful.")
        return jsonify(analysis_report), 200

    # 4. Robust Error Handling
    except FileNotFoundError:
        logging.critical("Slither executable not found in PATH.")
        return jsonify({"error": "Server configuration error: Slither is not installed."}), 500
    except subprocess.TimeoutExpired:
        logging.error("Slither analysis timed out.")
        return jsonify({"error": "Analysis timed out after 60 seconds."}), 500
    except json.JSONDecodeError:
        logging.error(f"Failed to parse Slither's JSON output. Raw output: {result.stdout}")
        return jsonify({"error": "Failed to parse Slither's output.", "raw_output": result.stdout}), 500
    except subprocess.CalledProcessError as e:
        logging.error(f"Slither execution failed. Stderr: {e.stderr}")
        return jsonify({"error": "Slither execution failed.", "details": e.stderr}), 500
    except Exception as e:
        logging.critical(f"An unexpected server error occurred: {str(e)}")
        return jsonify({"error": "An unexpected server error occurred.", "details": str(e)}), 500
    finally:
        # 5. Cleanup
        # Ensure the temporary file is always removed.
        if os.path.exists(file_path):
            os.remove(file_path)

if __name__ == '__main__':
    # This block is for local development only. Do not use `app.run` in production.
    app.run(host='0.0.0.0', port=8080, debug=True)

