import os
import logging
import tempfile
from pathlib import Path
import google.generativeai as genai
from pydub import AudioSegment
import requests
import json
from flask import current_app
import time
# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Allowed file extensions
ALLOWED_EXTENSIONS = {'wav', 'mp3', 'm4a', 'aac', 'ogg', 'flac'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_audio_file(file_path):
    """Validate if audio file is readable and not corrupted"""
    try:
        if not os.path.exists(file_path):
            logger.error(f"File does not exist: {file_path}")
            return False

        if os.path.getsize(file_path) == 0:
            logger.error(f"File is empty: {file_path}")
            return False

        # Try to load with pydub to check if it's valid
        audio = AudioSegment.from_file(file_path)
        logger.info(f"Audio file validated: {file_path} - Duration: {len(audio)}ms")
        return True

    except Exception as e:
        logger.error(f"Audio validation failed for {file_path}: {e}")
        return False

def convert_to_wav(input_audio_path, output_dir=None):
    """Convert audio file to WAV format with error handling"""
    try:
        if not validate_audio_file(input_audio_path):
            return None

        base = os.path.splitext(os.path.basename(input_audio_path))[0]

        if output_dir:
            wav_path = os.path.join(output_dir, f"{base}.wav")
        else:
            wav_path = os.path.join(tempfile.gettempdir(), f"{base}.wav")

        # If already WAV and valid, return original path
        if input_audio_path.lower().endswith('.wav'):
            return input_audio_path

        # Convert to WAV
        audio = AudioSegment.from_file(input_audio_path)
        audio.export(wav_path, format="wav")
        logger.info(f"Converted {input_audio_path} to {wav_path}")
        return wav_path

    except Exception as e:
        logger.error(f"Audio conversion failed: {e}")
        return None

def translate_audio(audio_file_path):
    """Transcribe audio using Sarvam AI API"""
    try:
        if not validate_audio_file(audio_file_path):
            return ""

        api_url = "https://api.sarvam.ai/speech-to-text-translate"
        headers = {"api-subscription-key": current_app.config['SARVAM_AI_API']}
        data = {
            "model": "saaras:v2",
            "with_diarization": False
        }

        with open(audio_file_path, 'rb') as f:
            files = {"file": ("audio.wav", f, "audio/wav")}
            response = requests.post(api_url, headers=headers, files=files, data=data)

        if response.status_code in [200, 201]:
            result = response.json()
            return result.get("transcript", "")
        else:
            logger.error(f"Translation failed: {response.status_code} - {response.text}")
            return ""

    except Exception as e:
        logger.error(f"Translation error: {e}")
        return ""

def classify_threat_with_gemini(transcript):
    """Classify threat type using Gemini AI with detailed analysis and location detection"""
    if not transcript or not transcript.strip():
        return {
            "threat_type": "unknown",
            "confidence": 0.0,
            "severity": "low",
            "analysis": "No transcript available for analysis",
            "keywords": [],
            "location_mentioned": None,
            "location_type": None,
            "location_confidence": 0.0
        }

    try:
        # Initialize Gemini model
        genai.configure(api_key=current_app.config['GEMINI_API_KEY'])
        model = genai.GenerativeModel('gemini-2.0-flash')

        # Create a detailed prompt for threat analysis with location detection
        prompt = f"""
        Analyze the following audio transcript for potential security threats, safety concerns, and location information. 
        Provide a detailed analysis in JSON format.

        Transcript: "{transcript}"

        Please analyze and classify this transcript according to the following:

        1. Threat Categories:
        - theft (stealing, robbery, snatching, burglary, pickpocketing)
        - land_dispute (property disputes, boundary issues, ownership conflicts)
        - domestic_violence (physical abuse, domestic fights, family violence)
        - harassment (stalking, threats, intimidation, bullying)
        - assault (physical attacks, violence against persons)
        - fraud (scams, financial fraud, cheating)
        - vandalism (property damage, destruction)
        - drug_related (drug dealing, substance abuse issues)
        - noise_complaint (loud music, disturbances)
        - medical_emergency (health emergencies, accidents)
        - fire_emergency (fire, smoke, burning)
        - unknown (cannot be classified or no threat detected)

        2. Location Information:
        - Identify any mentioned locations (streets, landmarks, buildings, areas, etc.)
        - Classify location type (residential, commercial, public space, etc.)
        - Determine confidence in location identification (0.0-1.0)

        Return your analysis in this exact JSON format:
        {{
            "threat_type": "category_name",
            "confidence": 0.0-1.0,
            "severity": "low|medium|high|critical",
            "analysis": "detailed explanation of your reasoning",
            "keywords": ["list", "of", "relevant", "keywords", "found"],
            "urgent": true/false,
            "recommended_action": "suggested response or action",
            "location": {{
                "mentioned": "exact location mentioned in transcript or null if none",
                "type": "residential|commercial|public_space|road|landmark|unknown",
                "confidence": 0.0-1.0,
                "details": "additional context about the location"
            }}
        }}

        Consider:
        1. Context and tone
        2. Specific location details
        3. Urgency of the situation
        4. Environmental factors
        5. Time references
        """

        # Generate response with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = model.generate_content(prompt)
                response_text = response.text.strip()

                # Parse JSON from response
                if response_text.startswith('```json'):
                    json_str = response_text.split('```json')[1].split('```')[0].strip()
                elif response_text.startswith('```'):
                    json_str = response_text.split('```')[1].strip()
                else:
                    json_str = response_text

                result = json.loads(json_str)

                # Validate and normalize result
                required_fields = ["threat_type", "confidence", "severity", "analysis", "location"]
                for field in required_fields:
                    if field not in result:
                        result[field] = "unknown" if field == "threat_type" else None

                if "location" not in result or not isinstance(result["location"], dict):
                    result["location"] = {
                        "mentioned": None,
                        "type": "unknown",
                        "confidence": 0.0,
                        "details": None
                    }

                # Ensure confidence values are floats between 0 and 1
                result["confidence"] = float(min(1.0, max(0.0, result["confidence"])))
                result["location"]["confidence"] = float(min(1.0, max(0.0, result["location"]["confidence"])))

                # Format final response
                return {
                    "threat_type": result["threat_type"],
                    "confidence": result["confidence"],
                    "severity": result["severity"],
                    "analysis": result["analysis"],
                    "keywords": result.get("keywords", []),
                    "urgent": result.get("urgent", False),
                    "recommended_action": result.get("recommended_action", ""),
                    "location_mentioned": result["location"]["mentioned"],
                    "location_type": result["location"]["type"],
                    "location_confidence": result["location"]["confidence"]
                }

            except Exception as e:
                logger.warning(f"Gemini API attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    return {
                        "threat_type": "unknown",
                        "confidence": 0.0,
                        "severity": "low",
                        "analysis": f"Analysis failed: {str(e)}",
                        "keywords": [],
                        "location_mentioned": None,
                        "location_type": None,
                        "location_confidence": 0.0
                    }
                time.sleep(2 ** attempt)  # Exponential backoff

    except Exception as e:
        logger.error(f"Gemini threat classification failed: {e}")
        return {
            "threat_type": "unknown",
            "confidence": 0.0,
            "severity": "low",
            "analysis": f"Classification failed: {str(e)}",
            "keywords": [],
            "location_mentioned": None,
            "location_type": None,
            "location_confidence": 0.0
        }    
    if not transcript or not transcript.strip():
        return {
            "threat_type": "unknown",
            "confidence": 0.0,
            "severity": "low",
            "analysis": "No transcript available for analysis",
            "keywords": []
        }

    try:
        # Initialize Gemini
        genai.configure(api_key=current_app.config['GEMINI_API_KEY'])
        model = genai.GenerativeModel('gemini-2.0-flash')

        prompt = f"""
        Analyze the following audio transcript for potential security threats and safety concerns. 
        Provide a detailed analysis in JSON format.

        Transcript: "{transcript}"

        Please analyze and classify this transcript according to the following categories:
        1. theft (stealing, robbery, snatching, burglary, pickpocketing)
        2. land_dispute (property disputes, boundary issues, ownership conflicts)
        3. domestic_violence (physical abuse, domestic fights, family violence)
        4. harassment (stalking, threats, intimidation, bullying)
        5. assault (physical attacks, violence against persons)
        6. fraud (scams, financial fraud, cheating)
        7. vandalism (property damage, destruction)
        8. drug_related (drug dealing, substance abuse issues)
        9. noise_complaint (loud music, disturbances)
        10. medical_emergency (health emergencies, accidents)
        11. fire_emergency (fire, smoke, burning)
        12. unknown (cannot be classified or no threat detected)

        Return your analysis in this exact JSON format:
        {{
            "threat_type": "category_name",
            "confidence": 0.0-1.0,
            "severity": "low|medium|high|critical",
            "analysis": "detailed explanation of your reasoning",
            "keywords": ["list", "of", "relevant", "keywords", "found"],
            "urgent": true/false,
            "recommended_action": "suggested response or action"
        }}
        """

        response = model.generate_content(prompt)
        response_text = response.text.strip()

        # Parse JSON from response
        if response_text.startswith('```json'):
            json_str = response_text.split('```json')[1].split('```')[0].strip()
        elif response_text.startswith('```'):
            json_str = response_text.split('```')[1].strip()
        else:
            json_str = response_text

        result = json.loads(json_str)

        # Validate and normalize result
        required_fields = ["threat_type", "confidence", "severity", "analysis"]
        for field in required_fields:
            if field not in result:
                result[field] = "unknown" if field == "threat_type" else "Not provided"

        # Ensure confidence is a float between 0 and 1
        try:
            result["confidence"] = float(result["confidence"])
            result["confidence"] = max(0.0, min(1.0, result["confidence"]))
        except:
            result["confidence"] = 0.5

        return result

    except Exception as e:
        logger.error(f"Gemini classification failed: {e}")
        return {
            "threat_type": "unknown",
            "confidence": 0.0,
            "severity": "low",
            "analysis": f"Classification failed: {str(e)}",
            "keywords": []
        }