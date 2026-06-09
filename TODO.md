# Qué falta en backend

## assets

- endpoint para listar activos
- seed inicial de activos
- búsqueda por símbolo/nombre
- validación de duplicados y normalización de symbol

## strategy

- CRUD completo de estrategia objetivo por portfolio
- validar que el portfolio pertenezca al usuario
- validar que cada asset_id exista
- validar que no haya activos repetidos
- validar que la suma de percentage sea coherente
- decisión de negocio: exigir 100% exacto o permitir menos de 100 mientras el usuario arma el portfolio

## transactions

- CRUD completo
- validaciones por tipo
- semántica clara de BUY/SELL/DIVIDEND/DEPOSIT/WITHDRAW
- reglas de consistencia:
  - BUY/SELL deberían requerir asset_id, quantity, price
  - DEPOSIT/WITHDRAW podrían no requerir quantity
  - hoy el esquema obliga quantity y price en todos los casos; eso hay que decidir si se mantiene o se corrige
- endpoint para historial ordenado y filtrable

## rebalanceo real

- endpoint tipo GET /api/portfolios/{id}/rebalance
- calcular valor actual por activo
- comparar contra estrategia objetivo
- devolver sugerencias accionables por activo
- definir fuente de precio actual:
  - manual
  - último transaction.price
  - API externa de mercado
- hoy solo existe la fórmula aislada, no el caso de uso completo

## auth backend

- middleware/dependencia ya existe, pero falta probar flujo real con access tokens del frontend
- falta decidir si ciertas rutas serán solo backend-internal con service_role
- falta respuesta consistente para 401/403

## cron y notificaciones

- decidir si el cron productivo lo dispara Vercel o Railway
- crear contrato exacto del header x-cron-secret
- definir mensaje final de negocio
- probar escritura en system_logs y envío real a Telegram
- decidir si el endpoint debe aceptar force=true solo en desarrollo/admin

## errores y observabilidad

- handler global de excepciones
- logging estructurado
- request ids
- mensajes de error uniformes
- health check más completo, incluyendo DB y dependencias externas

## pruebas

- unit tests de is_run_day
- unit tests de rebalanceo
- tests de auth dependency
- tests de CRUD de portfolios
- tests de integración contra DB
- hoy hay tests manuales de conexión en archivos sueltos; eso debe reemplazarse por tests reales
-  endpoint tipo GET /api/portfolios/{id}/rebalance
-  calcular valor actual por activo
-  comparar contra estrategia objetivo
-  devolver sugerencias accionables por activo
-  definir fuente de precio actual:
  - manual
  - último transaction.price
  - API externa de mercado
-  hoy solo existe la fórmula aislada, no el caso de uso completo
-  auth backend
  middleware/dependencia ya existe, pero falta probar flujo real con access tokens del frontend
  falta decidir si ciertas rutas serán solo backend-internal con service_role
  falta respuesta consistente para 401/403
  cron y notificaciones
  decidir si el cron productivo lo dispara Vercel o Railway
  crear contrato exacto del header x-cron-secret
  definir mensaje final de negocio
  probar escritura en system_logs y envío real a Telegram
  decidir si el endpoint debe aceptar force=true solo en desarrollo/admin
  errores y observabilidad
  handler global de excepciones
  logging estructurado
  request ids
  mensajes de error uniformes
  health check más completo, incluyendo DB y dependencias externas
  pruebas
  unit tests de is_run_day
  unit tests de rebalanceo
  tests de auth dependency
  tests de CRUD de portfolios
  tests de integración contra DB
  hoy hay tests manuales de conexión en archivos sueltos; eso debe reemplazarse por tests reales
