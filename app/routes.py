from flask import Blueprint, render_template, jsonify, request, send_file, current_app, flash, redirect, url_for
from app.models import db, AudioInput, ThreatAnalysisResult
from datetime import datetime
import io
import os

main = Blueprint('main', __name__)

@main.route('/')
def index():
    # Get processing statistics
    total_files = AudioInput.query.count()
    processed_files = AudioInput.query.filter_by(processed=True).count()
    pending_files = total_files - processed_files
    
    # Get recent analyses with error handling
    try:
        recent_results = ThreatAnalysisResult.query.order_by(
            ThreatAnalysisResult.created_at.desc()
        ).limit(10).all()
        
        # Add severity class for bootstrap styling
        for result in recent_results:
            result.severity_class = {
                'low': 'info',
                'medium': 'warning',
                'high': 'danger',
                'critical': 'dark',
                'error': 'secondary'
            }.get(result.severity.lower() if result.severity else 'error', 'secondary')
            
    except Exception as e:
        current_app.logger.error(f"Error fetching recent results: {e}")
        recent_results = []
        flash("Error loading recent analyses", "error")
    
    return render_template('index.html', 
                         recent_results=recent_results,
                         total_files=total_files,
                         processed_files=processed_files,
                         pending_files=pending_files)

@main.route('/results/<int:result_id>')
def view_result(result_id):
    try:
        result = ThreatAnalysisResult.query.get_or_404(result_id)
        
        # Add severity class for bootstrap styling
        result.severity_class = {
            'low': 'info',
            'medium': 'warning',
            'high': 'danger',
            'critical': 'dark',
            'error': 'secondary'
        }.get(result.severity.lower() if result.severity else 'error', 'secondary')
        
        return render_template('results.html', 
                             result=result)
    
    except Exception as e:
        current_app.logger.error(f"Error viewing result {result_id}: {e}")
        flash("Error loading analysis result", "error")
        return redirect(url_for('main.index'))

@main.route('/history')
def history():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 10
        
        pagination = ThreatAnalysisResult.query.order_by(
            ThreatAnalysisResult.created_at.desc()
        ).paginate(page=page, per_page=per_page)
        
        results = pagination.items
        
        # Add severity class for bootstrap styling
        for result in results:
            result.severity_class = {
                'low': 'info',
                'medium': 'warning',
                'high': 'danger',
                'critical': 'dark',
                'error': 'secondary'
            }.get(result.severity.lower() if result.severity else 'error', 'secondary')
        
        return render_template('history.html',
                             results=results,
                             page=page,
                             total_pages=pagination.pages)
    
    except Exception as e:
        current_app.logger.error(f"Error loading history: {e}")
        flash("Error loading analysis history", "error")
        return redirect(url_for('main.index'))

@main.route('/api/status')
def get_status():
    try:
        total_files = AudioInput.query.count()
        processed_files = AudioInput.query.filter_by(processed=True).count()
        pending_files = total_files - processed_files
        
        latest_results = ThreatAnalysisResult.query.order_by(
            ThreatAnalysisResult.created_at.desc()
        ).limit(5).all()
        
        results = []
        for result in latest_results:
            results.append({
                'id': result.id,
                'filename': result.audio_input.filename if result.audio_input else 'Unknown',
                'threat_type': result.threat_type,
                'confidence': float(result.confidence) if result.confidence else 0.0,
                'severity': result.severity,
                'created_at': result.created_at.strftime('%Y-%m-%d %H:%M:%S') if result.created_at else None
            })
        
        return jsonify({
            'total_files': total_files,
            'processed_files': processed_files,
            'pending_files': pending_files,
            'latest_results': results,
            'current_time': '2025-06-13 05:37:06'
        })
    
    except Exception as e:
        current_app.logger.error(f"Error getting status: {e}")
        return jsonify({
            'error': 'Error fetching status',
            'current_time': '2025-06-13 05:37:06'
        }), 500

@main.route('/download/<int:result_id>')
def download_audio(result_id):
    try:
        result = ThreatAnalysisResult.query.get_or_404(result_id)
        
        if not result.audio_file:
            flash("No audio file available for download", "error")
            return redirect(url_for('main.view_result', result_id=result_id))
        
        filename = f"{result.audio_input.filename}_processed.wav" if result.audio_input else "processed_audio.wav"
        
        return send_file(
            io.BytesIO(result.audio_file),
            mimetype='audio/wav',
            as_attachment=True,
            download_name=filename
        )
    
    except Exception as e:
        current_app.logger.error(f"Error downloading audio {result_id}: {e}")
        flash("Error downloading audio file", "error")
        return redirect(url_for('main.view_result', result_id=result_id))

@main.route('/api/threats/summary')
def get_threat_summary():
    try:
        # Get threat type distribution
        threat_counts = db.session.query(
            ThreatAnalysisResult.threat_type,
            db.func.count(ThreatAnalysisResult.id)
        ).group_by(ThreatAnalysisResult.threat_type).all()
        
        # Get severity distribution
        severity_counts = db.session.query(
            ThreatAnalysisResult.severity,
            db.func.count(ThreatAnalysisResult.id)
        ).group_by(ThreatAnalysisResult.severity).all()
        
        # Get urgent threats count
        urgent_count = ThreatAnalysisResult.query.filter_by(urgent=True).count()
        
        return jsonify({
            'threat_distribution': dict(threat_counts),
            'severity_distribution': dict(severity_counts),
            'urgent_threats': urgent_count,
            'current_time': '2025-06-13 05:37:06'
        })
    
    except Exception as e:
        current_app.logger.error(f"Error getting threat summary: {e}")
        return jsonify({
            'error': 'Error fetching threat summary',
            'current_time': '2025-06-13 05:37:06'
        }), 500

@main.route('/api/threats/urgent')
def get_urgent_threats():
    try:
        urgent_threats = ThreatAnalysisResult.query.filter_by(
            urgent=True
        ).order_by(ThreatAnalysisResult.created_at.desc()).limit(10).all()
        
        results = []
        for threat in urgent_threats:
            results.append({
                'id': threat.id,
                'filename': threat.audio_input.filename if threat.audio_input else 'Unknown',
                'threat_type': threat.threat_type,
                'severity': threat.severity,
                'created_at': threat.created_at.strftime('%Y-%m-%d %H:%M:%S') if threat.created_at else None,
                'recommended_action': threat.recommended_action
            })
        
        return jsonify({
            'urgent_threats': results,
            'current_time': '2025-06-13 05:37:06'
        })
    
    except Exception as e:
        current_app.logger.error(f"Error getting urgent threats: {e}")
        return jsonify({
            'error': 'Error fetching urgent threats',
            'current_time': '2025-06-13 05:37:06'
        }), 500

@main.route('/api/threats/by_type/<threat_type>')
def get_threats_by_type(threat_type):
    try:
        threats = ThreatAnalysisResult.query.filter_by(
            threat_type=threat_type
        ).order_by(ThreatAnalysisResult.created_at.desc()).limit(10).all()
        
        results = []
        for threat in threats:
            results.append({
                'id': threat.id,
                'filename': threat.audio_input.filename if threat.audio_input else 'Unknown',
                'confidence': float(threat.confidence) if threat.confidence else 0.0,
                'severity': threat.severity,
                'created_at': threat.created_at.strftime('%Y-%m-%d %H:%M:%S') if threat.created_at else None
            })
        
        return jsonify({
            'threats': results,
            'threat_type': threat_type,
            'current_time': '2025-06-13 05:37:06'
        })
    
    except Exception as e:
        current_app.logger.error(f"Error getting threats by type {threat_type}: {e}")
        return jsonify({
            'error': f'Error fetching threats of type {threat_type}',
            'current_time': '2025-06-13 05:37:06'
        }), 500

@main.route('/api/processing/status')
def get_processing_status():
    try:
        # Get processing statistics
        total = AudioInput.query.count()
        processed = AudioInput.query.filter_by(processed=True).count()
        pending = total - processed
        
        # Get latest processed files
        latest_processed = AudioInput.query.filter_by(
            processed=True
        ).order_by(AudioInput.created_at.desc()).limit(5).all()
        
        latest_list = []
        for audio in latest_processed:
            latest_list.append({
                'id': audio.id,
                'filename': audio.filename,
                'processed_at': audio.created_at.strftime('%Y-%m-%d %H:%M:%S') if audio.created_at else None
            })
        
        return jsonify({
            'total_files': total,
            'processed_files': processed,
            'pending_files': pending,
            'latest_processed': latest_list,
            'current_time': '2025-06-13 05:37:06'
        })
    
    except Exception as e:
        current_app.logger.error(f"Error getting processing status: {e}")
        return jsonify({
            'error': 'Error fetching processing status',
            'current_time': '2025-06-13 05:37:06'
        }), 500
@main.route('/api/nearby-incidents')
def get_nearby_incidents():
    try:
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))
        radius = float(request.args.get('radius', 1.0))  # Default 1km radius
        
        # Get incidents within radius
        # This is a simplified version - you'll need to implement proper geo-querying
        recent_results = ThreatAnalysisResult.query.filter(
            ThreatAnalysisResult.created_at >= (datetime.utcnow() - timedelta(days=30))
        ).all()
        
        # Calculate incident statistics
        total_incidents = len(recent_results)
        severity_counts = {
            'low': 0,
            'medium': 0,
            'high': 0,
            'critical': 0
        }
        threat_types = {}
        
        for result in recent_results:
            if result.severity:
                severity_counts[result.severity.lower()] += 1
            if result.threat_type:
                threat_types[result.threat_type] = threat_types.get(result.threat_type, 0) + 1
        
        # Determine area risk level
        risk_score = (
            severity_counts['critical'] * 4 +
            severity_counts['high'] * 3 +
            severity_counts['medium'] * 2 +
            severity_counts['low']
        ) / max(total_incidents, 1)
        
        risk_level = 'Low'
        if risk_score > 3:
            risk_level = 'Critical'
        elif risk_score > 2:
            risk_level = 'High'
        elif risk_score > 1:
            risk_level = 'Medium'
        
        # Get most common threat type
        common_type = max(threat_types.items(), key=lambda x: x[1])[0] if threat_types else 'None'
        
        return jsonify({
            'incidents': [
                {
                    'lat': lat + (random.random() - 0.5) * 0.01,  # Simulate nearby incidents
                    'lon': lon + (random.random() - 0.5) * 0.01,
                    'intensity': random.random()
                }
                for _ in range(min(total_incidents, 20))
            ],
            'statistics': {
                'total_incidents': total_incidents,
                'recent_incidents': len(recent_results),
                'severity_level': risk_level,
                'common_type': common_type
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting nearby incidents: {e}")
        return jsonify({
            'error': 'Error fetching nearby incidents',
            'current_time': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        }), 500
    
@main.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@main.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500