# Contexto

Un acta de la mesa de contratación de un acuerdo marco del Servicio Madrileño de Salud, con 15 lotes de desfibriladores implantables y electrodos. Es un documento público. Incluye texto, tablas apaisadas que ocupan varias páginas (Anexos 1 y 2) y un informe técnico escaneado (Anexo 3).

# Objetivo

Desarrollar un proceso que extraiga automáticamente la **concurrencia** del acta, es decir, quién se presentó a cada lote, qué ofertó y qué puntuación obtuvo.

# Qué hay que extraer

Por cada lote y cada licitador:

- Número de lote y, si existe, número de orden o sublote (1.1, 1.2…)
- Licitador: nombre y NIF
- Precio unitario de licitación y precio unitario ofertado (sin IVA)
- Importe total de licitación y total ofertado (sin IVA)
- Puntos del criterio precio, puntos de criterios cualitativos y puntuación total
- Orden de prelación y si es el adjudicatario propuesto
- Si está incurso en presunción de baja anormal o temeraria, y en qué posiciones
Además, a nivel de expediente: número de expediente, objeto, órgano de contratación y fecha de la mesa.

# Requisitos

1. **Proceso automático y reutilizable**. Debe funcionar con otras actas similares, así que no vale codificar a mano los datos de esta.
2. **Exactitud de las cifras**. Ningún importe ni puntuación puede salir redondeado, corregido ni inventado. Cada cifra debe poder localizarse en el documento (página de origen).
3. **Validaciones automáticas**. Comprueba la coherencia de lo extraído: que las puntuaciones cuadren, que el orden de prelación sea consistente con las puntuaciones, que lo ofertado no supere lo licitado, etc. Las incidencias que encuentres deben ir a un fichero aparte; no las corrijas en silencio.
4. **Control de errores**. Si una página no se puede leer o un dato es dudoso, el proceso no debe detenerse: lo registra y continúa.

# Entregables

- Repositorio Git (GitHub o similar) con commits a lo largo del desarrollo, no un único commit final.
- concurrencia.json y concurrencia.xlsx, con una fila por lote, orden y licitador.
- incidencias.json, con los problemas y las inconsistencias detectadas.
- README.md que explique cómo ejecutarlo, qué decisiones de diseño has tomado y por qué, qué herramientas usas para el OCR y las tablas, el coste aproximado por documento si usas modelos de pago, y qué fallaría o cambiarías para procesar 160 actas de distintos organismos.
