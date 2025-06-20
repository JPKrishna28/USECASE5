import threading
import time
from datetime import datetime, timedelta
import tempfile
import os
from flask import current_app
from app import db
from app.models import AudioInput, ThreatAnalysisResult
from app.utils import convert_to_wav, translate_audio, classify_threat_with_gemini
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Create a lock for processing
processing_lock = threading.Lock()
# Flag to track if the background task is running
is_running = False

def create_db_session():
    """Create a new database session"""
    engine = create_engine(current_app.config['SQLALCHEMY_DATABASE_URI'])
    Session = sessionmaker(bind=engine)
    return Session()

def process_audio_files():
    """Process unprocessed audio files from the database"""
    global is_running
    logger.info("Starting audio processing thread")
    
    while True:
        try:
            # Try to acquire the lock
            if not processing_lock.acquire(blocking=False):
                logger.info("Another processing thread is already running")
                time.sleep(600)  # Wait 10 minutes before trying again
                continue

            try:
                # Create a new session for this iteration
                session = create_db_session()
                
                # Get unprocessed audio files that haven't been processed in the last minute
                cutoff_time = datetime.utcnow() - timedelta(minutes=1)
                unprocessed_files = (
                    session.query(AudioInput)
                    .filter(AudioInput.processed == False)
                    .filter(
                        # Either the file has never been processed
                        # or it was processed more than a minute ago
                        (AudioInput.last_processed_at.is_(None)) |
                        (AudioInput.last_processed_at < cutoff_time)
                    )
                    .all()
                )
                
                if unprocessed_files:
                    logger.info(f"Found {len(unprocessed_files)} unprocessed audio files")
                    
                    for audio_input in unprocessed_files:
                        try:
                            # Update last processed timestamp immediately
                            audio_input.last_processed_at = datetime.utcnow()
                            session.commit()

                            # Check if this file has already been processed
                            existing_result = session.query(ThreatAnalysisResult).filter_by(
                                audio_id=audio_input.id
                            ).first()

                            if existing_result:
                                logger.info(f"File {audio_input.filename} already processed, skipping")
                                continue

                            # Create temporary directory for processing
                            with tempfile.TemporaryDirectory() as temp_dir:
                                # Save audio file temporarily
                                temp_path = os.path.join(temp_dir, audio_input.filename)
                                with open(temp_path, 'wb') as f:
                                    f.write(audio_input.audio_file)
                                
                                logger.info(f"Processing file: {audio_input.filename}")
                                
                                # Convert to WAV if needed
                                wav_path = convert_to_wav(temp_path, temp_dir)
                                if not wav_path:
                                    raise Exception("Failed to convert audio file")
                                
                                # Process the audio
                                transcript = translate_audio(wav_path)
                                threat_analysis = classify_threat_with_gemini(transcript)
                                
                                # Read processed audio file
                                with open(wav_path, 'rb') as f:
                                    processed_audio_data = f.read()
                                
                                # Create result entry
                                result = ThreatAnalysisResult(
                                    audio_id=audio_input.id,
                                    transcript=transcript,
                                    threat_type=threat_analysis['threat_type'],
                                    confidence=threat_analysis['confidence'],
                                    severity=threat_analysis['severity'],
                                    analysis=threat_analysis['analysis'],
                                    keywords=threat_analysis.get('keywords', []),
                                    urgent=threat_analysis.get('urgent', False),
                                    recommended_action=threat_analysis.get('recommended_action', ''),
                                    audio_file=processed_audio_data,
                                    created_at=datetime.utcnow()
                                )
                                session.add(result)
                                
                                # Mark as processed
                                audio_input.processed = True
                                
                                # Commit changes for this file
                                session.commit()
                                logger.info(f"Successfully processed file: {audio_input.filename}")
                                
                        except Exception as e:
                            logger.error(f"Error processing file {audio_input.filename}: {e}")
                            try:
                                # Create error result only if no result exists
                                existing_error = session.query(ThreatAnalysisResult).filter_by(
                                    audio_id=audio_input.id
                                ).first()
                                
                                if not existing_error:
                                    error_result = ThreatAnalysisResult(
                                        audio_id=audio_input.id,
                                        threat_type='error',
                                        confidence=0.0,
                                        severity='low',
                                        analysis=f'Error processing file: {str(e)}',
                                        error_message=str(e),
                                        created_at=datetime.utcnow()
                                    )
                                    session.add(error_result)
                                    audio_input.processed = True
                                    session.commit()
                            except Exception as inner_e:
                                logger.error(f"Error creating error result: {inner_e}")
                                session.rollback()
                else:
                    logger.info("No unprocessed audio files found")
                
                # Close the session
                session.close()
                
            finally:
                # Always release the lock
                processing_lock.release()
                
        except Exception as e:
            logger.error(f"Background task error: {e}")
            if 'session' in locals():
                session.close()
            if processing_lock.locked():
                processing_lock.release()
        
        # Wait for 10 minutes before next check
        logger.info("Waiting 10 minutes before next check...")
        time.sleep(600)  # 600 seconds = 10 minutes

def start_background_processing(app):
    """Start the background processing thread with app context"""
    global is_running
    
    if is_running:
        logger.info("Background processing already running")
        return
    
    def run_processing():
        with app.app_context():
            process_audio_files()
    
    is_running = True
    thread = threading.Thread(target=run_processing, daemon=True)
    thread.start()
    logger.info("Background processing thread started")