# this is the backend that helps us in verifing the image

from flask import Flask, request, jsonify
from web3 import Web3
import json, hashlib
from flask_cors import CORS
import sqlite3
import os
from dotenv import load_dotenv

app = Flask(__name__)
CORS(app, origins=["http://localhost:3000"])

# blockchain connection is made
web3 = Web3(Web3.HTTPProvider('http://127.0.0.1:8545'))

# Abi loading
with open('ImageAuthABI.json', 'r') as f:
    abi = json.load(f)

contract_address = web3.to_checksum_address('0x5FbDB2315678afecb367f032d93F642f64180aa3')  # Update if needed
contract = web3.eth.contract(address=contract_address, abi=abi)


load_dotenv()  # Looks for .env in the same directory

sender_address = os.getenv("SENDER_ADDRESS")
if not sender_address:
    raise EnvironmentError("[ERROR] SENDER_ADDRESS not found in .env file!")
else:
    print("[DEBUG] SENDER_ADDRESS loaded successfully:", sender_address)

private_key = os.getenv("PRIVATE_KEY")

if not private_key:
    raise EnvironmentError("[ERROR] PRIVATE_KEY not found in .env file!")
else:
    print("[DEBUG] PRIVATE_KEY loaded successfully")

# local DB setup
DB_PATH = 'metadata.db'
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS images (
                            hash TEXT PRIMARY KEY,
                            metadata TEXT,
                            timestamp INTEGER,
                            tx_hash TEXT
                        )''')

init_db()

@app.route('/upload', methods=['POST'])
def upload_image():
    try:
        file = request.files['image']
        metadata = request.form.get('metadata', '')
        image_bytes = file.read()
        image_hash = hashlib.sha256(image_bytes).hexdigest()

        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM images WHERE hash=?", (image_hash,))
            if cursor.fetchone():
                return jsonify({'error': 'Image already registered locally'}), 400

        nonce = web3.eth.get_transaction_count(sender_address)
        txn = contract.functions.registerImage(image_hash, metadata).build_transaction({
            'from': sender_address,
            'nonce': nonce,
            'gas': 2000000,
            'gasPrice': web3.to_wei('20', 'gwei')
        })

        signed_txn = web3.eth.account.sign_transaction(txn, private_key=private_key)
        tx_hash = web3.eth.send_raw_transaction(signed_txn.raw_transaction)
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT INTO images (hash, metadata, timestamp, tx_hash) VALUES (?, ?, ?, ?)",
                         (image_hash, metadata, receipt['blockNumber'], tx_hash.hex()))

        return jsonify({
            'hash': image_hash,
            'tx_hash': tx_hash.hex(),
            'status': 'registered',
            'metadata': metadata
        })
    except Exception as e:
        print("Upload failed:", str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/verify', methods=['POST'])
def verify_image():
    try:
        data = request.get_json()
        image_hash = data.get('hash')
        print("\U0001f9ea Verifying hash:", image_hash)

        verified, timestamp, metadata = contract.functions.verifyImage(image_hash).call()

        print("\u2705 Verification success:", verified, timestamp, metadata)

        return jsonify({
            'verified': verified,
            'timestamp': timestamp,
            'metadata': metadata
        })
    except Exception as e:
        print("\u274c Verification failed:", str(e))
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)

