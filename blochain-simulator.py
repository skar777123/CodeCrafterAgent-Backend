import os
import subprocess
import json
import logging
import atexit
from flask import Flask, request, jsonify

# --- Configuration and Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
app = Flask(__name__)

PRIVATE_KEY = os.environ.get("FOUNDRY_PRIVATE_KEY")
if not PRIVATE_KEY:
    logging.error("FATAL: FOUNDRY_PRIVATE_KEY environment variable not set.")

ANVIL_PROCESS = None
try:
    anvil_command = ["anvil", "--hardfork", "shanghai"] 
    ANVIL_PROCESS = subprocess.Popen(
        anvil_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    logging.info(f"Anvil process started successfully with PID: {ANVIL_PROCESS.pid}")
except FileNotFoundError:
    logging.error("FATAL: Anvil is not installed or not in PATH.")
    exit(1)

def cleanup():
    if ANVIL_PROCESS:
        logging.info("Terminating Anvil process...")
        ANVIL_PROCESS.terminate()
        ANVIL_PROCESS.wait()
atexit.register(cleanup)

# --- API Endpoint ---
@app.route('/simulate', methods=['POST'])
def simulate():
    logging.info("Received request on /simulate endpoint.")
    if not PRIVATE_KEY:
        return jsonify({"error": "Server configuration error: Private key not set."}), 500
        
    try:
        data = request.json
        bytecode = data.get('bytecode')
        transactions = data.get('transactions', [])

        if not bytecode:
            return jsonify({"error": "Invalid payload: 'bytecode' key is missing."}), 400

        # Deploy the contract with the CORRECT argument order.
        # All options must come before the '--create' flag.
        deploy_cmd = [
            'cast', 'send',
            '--private-key', PRIVATE_KEY, 
            '--rpc-url', 'http://127.0.0.1:8545', 
            '--json',
            '--create', # This flag now comes after all other options
            bytecode
        ]
        deploy_result = subprocess.run(deploy_cmd, capture_output=True, text=True, check=True, timeout=30)
        deploy_info = json.loads(deploy_result.stdout)
        contract_address = deploy_info['contractAddress']

        logging.info(f"Contract deployed at address: {contract_address}")
        simulation_results = {
            "deployment_gas_used": deploy_info.get('gasUsed'),
            "contract_address": contract_address, 
            "outcomes": []
        }

        # Execute each transaction
        for i, tx in enumerate(transactions):
            if not isinstance(tx, dict) or 'function_signature' not in tx or 'args' not in tx or not isinstance(tx['args'], list):
                return jsonify({"error": f"Invalid format for transaction at index {i}."}), 400

            try:
                send_cmd = [
                    'cast', 'send', '--private-key', PRIVATE_KEY, '--rpc-url', 'http://127.0.0.1:8545', '--json',
                    contract_address, tx['function_signature']
                ]
                if tx['args']:
                    send_cmd.extend(tx['args'])

                result = subprocess.run(send_cmd, capture_output=True, text=True, check=True, timeout=30)
                tx_info = json.loads(result.stdout)
                simulation_results['outcomes'].append({
                    "transaction": tx, "status": "success", "tx_hash": tx_info['transactionHash']
                })

            except subprocess.CalledProcessError as e:
                logging.error(f"Transaction at index {i} failed: {e.stderr}")
                simulation_results['outcomes'].append({
                    "transaction": tx, "status": "failed", "error_details": e.stderr.strip()
                })

        return jsonify(simulation_results), 200

    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Contract deployment failed.", "details": e.stderr.strip()}), 400
    except Exception as e:
        return jsonify({"error": "An internal server error occurred.", "details": str(e)}), 500
