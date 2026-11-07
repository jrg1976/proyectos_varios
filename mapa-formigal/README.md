# Formigal 3D

Mapa 3D interactivo (no oficial) de la estación de Formigal.

- `web/`: la página (three.js) y sus datos ya preparados. Para verla en local:
  `cd web && python3 -m http.server` y abrir http://localhost:8000
- `scripts/`: cómo se generan los datos.

## Regenerar los datos

1. Descargar OSM por teselas (la API de OSM limita a 50.000 nodos por petición) a `data_raw/osm_*.xml`
   con `https://api.openstreetmap.org/api/0.6/map?bbox=...` cubriendo lon -0.43…-0.30, lat 42.74…42.83.
2. Relieve IGN MDT05 (WCS):
   `https://servicios.idee.es/wcs-inspire/mdt?SERVICE=WCS&REQUEST=GetCoverage&VERSION=2.0.1&CoverageId=Elevacion4258_5&subset=Lat(42.735,42.815)&subset=Long(-0.455,-0.33)&format=image/tiff` → `data_raw/mdt.tif`
3. Ortofoto PNOA (WMS):
   `https://www.ign.es/wms-inspire/pnoa-ma?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS=OI.OrthoimageCoverage&STYLES=&CRS=EPSG:4326&BBOX=42.735,-0.455,42.815,-0.33&WIDTH=4096&HEIGHT=3570&FORMAT=image/jpeg` → `data_raw/ortho.jpg`
4. `python3 scripts/parse_osm.py data_raw data_raw/feats.json`
5. `python3 scripts/build_assets.py data_raw build` y copiar `build/*` (menos `height.bin`) a `web/`.

## Fuentes y licencias

- Pistas, remontes, cimas y restaurantes: © colaboradores de OpenStreetMap (ODbL).
- Relieve MDT05 y ortofoto PNOA: © Instituto Geográfico Nacional (CC BY 4.0).
- La vista «Invierno» es una recreación a partir del relieve y la ortofoto.
