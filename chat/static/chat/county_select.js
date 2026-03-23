function initMap() {
    if (typeof L === "undefined") {
        console.error("Leaflet not loaded");
        return;
    }

    const mapElement = document.getElementById("map");
    if (!mapElement) {
        console.error("#map element not found");
        return;
    }

    // Pass the DOM element so Leaflet never resolves id before element exists
    const map = L.map(mapElement, {
        zoomControl: false,
        attributionControl: false
    }).setView([39.3, -111.7], 7);

    const pastelColors = [
        "#E8EDF5",
        "#F0EAF5",
        "#F5F2EA",
        "#E8F2EA"
    ];

    function style(feature) {
        const index = feature.properties.COUNTYFP
            ? parseInt(feature.properties.COUNTYFP, 10) % pastelColors.length
            : 0;

        return {
            fillColor: pastelColors[index],
            fillOpacity: 0.92,
            color: "#c8c8d0",
            weight: 1.25
        };
    }

    fetch(window.GEOJSON_URL)
        .then(res => res.json())
        .then(data => {

            const geoLayer = L.geoJSON(data, {
                style: style,
                onEachFeature: function (feature, layer) {

                    const name = feature.properties.NAME;

                    layer.on({
                        mouseover: function (e) {
                            e.target.setStyle({
                                fillColor: "#d8dce6",
                                color: "#9ca3af",
                                weight: 2,
                                fillOpacity: 0.95
                            });
                        },
                        mouseout: function (e) {
                            geoLayer.resetStyle(e.target);
                        },
                        click: function () {
                            localStorage.setItem("selected_county", name);
                            window.location.href = "/chat/?county=" + encodeURIComponent(name);
                        }
                    });

                    layer.bindTooltip(name, {
                        permanent: true,
                        direction: "center",
                        className: "county-label"
                    });
                }
            });

            geoLayer.addTo(map);
            map.fitBounds(geoLayer.getBounds(), { padding: [30, 30] });
        })
        .catch(err => console.error("GeoJSON load error:", err));
}

// Run only after DOM is ready; if already loaded, defer one tick so #map is in the DOM
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initMap);
} else {
    setTimeout(initMap, 0);
}

