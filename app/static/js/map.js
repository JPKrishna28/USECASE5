// Create a global namespace for our map functionality
window.ThreatMap = {
    map: null,
    marker: null,
    geocoder: null,
    currentLocation: null,

    async geocodeLocation(location) {
        return new Promise((resolve, reject) => {
            this.geocoder.geocode(location, function(results) {
                if (results && results.length > 0) {
                    resolve({
                        lat: results[0].center.lat,
                        lon: results[0].center.lng
                    });
                } else {
                    reject('Location not found');
                }
            });
        });
    },

    getSeverityColor(severity) {
        const colors = {
            'low': '#3498db',
            'medium': '#f1c40f',
            'high': '#e74c3c',
            'critical': '#c0392b'
        };
        return colors[severity.toLowerCase()] || '#95a5a6';
    },

    async loadNearbyIncidents(lat, lon) {
        try {
            const response = await fetch(`/api/nearby-incidents?lat=${lat}&lon=${lon}`);
            const data = await response.json();
            
            this.updateLocationStats(data.statistics);
            
            if (data.incidents && data.incidents.length > 0) {
                const heatData = data.incidents.map(incident => [
                    incident.lat,
                    incident.lon,
                    incident.intensity
                ]);
                L.heatLayer(heatData, {
                    radius: 25,
                    blur: 15,
                    maxZoom: 10
                }).addTo(this.map);
            }
        } catch (error) {
            console.error('Error loading nearby incidents:', error);
        }
    },

    updateLocationStats(stats) {
        if (!stats) return;
        
        const statsElement = document.getElementById('locationStats');
        if (!statsElement) return;

        const statsHtml = `
            <div class="col-md-3">
                <div class="card">
                    <div class="card-body text-center">
                        <h3>${stats.total_incidents}</h3>
                        <p>Total Incidents</p>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card">
                    <div class="card-body text-center">
                        <h3>${stats.recent_incidents}</h3>
                        <p>Recent (30 days)</p>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card">
                    <div class="card-body text-center">
                        <h3>${stats.severity_level}</h3>
                        <p>Area Risk Level</p>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card">
                    <div class="card-body text-center">
                        <h3>${stats.common_type}</h3>
                        <p>Common Incident</p>
                    </div>
                </div>
            </div>
        `;
        
        statsElement.innerHTML = statsHtml;
    },

    centerMap() {
        console.log('Centering map...', this.marker, this.currentLocation);
        if (this.marker && this.currentLocation) {
            this.map.setView([this.currentLocation.lat, this.currentLocation.lon], 15);
        }
    },

    async initialize(location_mentioned, threat_type, severity) {
        if (!location_mentioned) return;

        try {
            // Initialize map
            this.map = L.map('map').setView([20.5937, 78.9629], 5);

            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                maxZoom: 19,
                attribution: '© OpenStreetMap contributors'
            }).addTo(this.map);

            this.geocoder = L.Control.Geocoder.nominatim();

            const searchControl = L.Control.geocoder({
                geocoder: this.geocoder,
                defaultMarkGeocode: false
            })
            .on('markgeocode', (e) => {
                const bbox = e.geocode.bbox;
                const poly = L.polygon([
                    bbox.getSouthEast(),
                    bbox.getNorthEast(),
                    bbox.getNorthWest(),
                    bbox.getSouthWest()
                ]);
                this.map.fitBounds(poly.getBounds());
            })
            .addTo(this.map);

            const result = await this.geocodeLocation(location_mentioned);
            if (result) {
                this.currentLocation = result;
                const { lat, lon } = result;
                
                this.map.setView([lat, lon], 15);

                const markerIcon = L.divIcon({
                    className: 'custom-div-icon',
                    html: `<div style="background-color: ${this.getSeverityColor(severity)}; 
                                    padding: 10px; 
                                    border-radius: 50%; 
                                    border: 2px solid white;
                                    box-shadow: 0 2px 5px rgba(0,0,0,0.3);">
                            <i class="fas fa-exclamation-triangle" style="color: white;"></i>
                           </div>`,
                    iconSize: [30, 30],
                    iconAnchor: [15, 15]
                });

                this.marker = L.marker([lat, lon], { icon: markerIcon })
                    .addTo(this.map)
                    .bindPopup(`
                        <strong>${threat_type}</strong><br>
                        Location: ${location_mentioned}<br>
                        Severity: ${severity}
                    `);

                await this.loadNearbyIncidents(lat, lon);
            }
        } catch (error) {
            console.error('Map initialization error:', error);
            const mapElement = document.getElementById('map');
            if (mapElement) {
                mapElement.innerHTML = 
                    '<div class="alert alert-danger">Error loading map. Please try again later.</div>';
            }
        }
    }
};