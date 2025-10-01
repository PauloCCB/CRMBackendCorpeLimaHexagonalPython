# 🎓 Guía para Estudiantes: Implementar Caché Persistente con Redis

## 📚 ¿Qué vamos a lograr?

Implementaremos un **sistema de caché con Redis** para reducir el tiempo de respuesta del endpoint `/obtener-ruc/{ruc}` de **10-30 segundos** a menos de **100 milisegundos** cuando el RUC ya fue consultado anteriormente.

### ¿Por qué Redis?

**Redis** es una base de datos en memoria (muy rápida) que actúa como un "almacén temporal" de datos. Imagínalo como una libreta donde guardas las respuestas de los exámenes ya resueltos, para no tener que resolverlos de nuevo.

**Beneficios:**
- ⚡ **Velocidad**: Redis guarda datos en memoria RAM (super rápido)
- 💾 **Persistencia**: Los datos sobreviven aunque reinicies tu aplicación
- 🔄 **Expiración automática**: Puedes configurar que los datos se borren después de X días
- 📦 **Fácil integración**: Se conecta con Python en pocas líneas de código

---

## 🗺️ Arquitectura de la Solución

### Antes (sin caché):
```
Usuario → FastAPI → Scraper (Selenium) → SUNAT → Respuesta (10-30 seg)
```

### Después (con Redis):
```
Usuario → FastAPI → Redis (¿existe?)
                      ├─ SÍ  → Respuesta instantánea (< 100ms) ✅
                      └─ NO  → Scraper → SUNAT → Guardar en Redis → Respuesta
```

---

## 📋 Pasos de Implementación

### **PASO 1: Configurar Docker Compose** 🐳

Docker Compose nos permite manejar **múltiples contenedores** (tu backend + Redis) de forma sencilla.

#### 1.1 Crear archivo `docker-compose.yml`

Crea este archivo en la **raíz del proyecto** (al mismo nivel que `Dockerfile`):

```yaml
version: '3.8'

services:
  # ========================================
  # SERVICIO DE REDIS
  # ========================================
  redis:
    image: redis:7-alpine  # Imagen oficial de Redis (versión ligera)
    container_name: crm_redis
    ports:
      - "6379:6379"  # Puerto por defecto de Redis
    volumes:
      - redis_data:/data  # Aquí se guardan los datos de forma persistente
    command: redis-server --appendonly yes  # Habilita persistencia en disco
    networks:
      - crm_network
    restart: unless-stopped  # Se reinicia automáticamente si falla
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3

  # ========================================
  # SERVICIO DEL BACKEND (FastAPI)
  # ========================================
  backend:
    build: .  # Usa el Dockerfile en la raíz del proyecto
    container_name: crm_backend
    ports:
      - "8000:8000"  # Puerto de FastAPI
    environment:
      # URL de conexión a Redis (usa el nombre del servicio "redis")
      - REDIS_URL=redis://redis:6379
      - PYTHONUNBUFFERED=1
    depends_on:
      redis:
        condition: service_healthy  # Espera a que Redis esté listo
    networks:
      - crm_network
    restart: unless-stopped

# ========================================
# VOLÚMENES (Persistencia de datos)
# ========================================
volumes:
  redis_data:
    driver: local  # Los datos de Redis se guardan en tu disco local

# ========================================
# REDES (Para que los contenedores se comuniquen)
# ========================================
networks:
  crm_network:
    driver: bridge
```

#### 💡 Explicación para estudiantes:

- **services**: Aquí defines cada "aplicación" (Redis y Backend)
- **image**: La imagen Docker a usar (Redis 7 en versión Alpine, que es ligera)
- **ports**: Mapea puertos del contenedor a tu máquina (6379 es el puerto estándar de Redis)
- **volumes**: Guarda los datos de Redis en tu disco para que no se pierdan
- **networks**: Permite que Backend y Redis se "vean" entre sí
- **depends_on**: Backend esperará a que Redis esté listo antes de iniciar
- **healthcheck**: Verifica que Redis esté funcionando correctamente

---

### **PASO 2: Instalar Dependencias de Python** 📦

#### 2.1 Agregar Redis a `requirements.txt`

Abre tu archivo `requirements.txt` y agrega:

```txt
redis==5.0.1
```

#### 2.2 Instalar localmente (para desarrollo)

```bash
pip install redis==5.0.1
```

---

### **PASO 3: Crear Servicio de Caché** 🛠️

Vamos a crear un archivo dedicado para manejar Redis de forma organizada.

#### 3.1 Crear archivo `app/infrastructure/cache/redis_cache.py`

```python
"""
Servicio de caché con Redis
"""
import redis
import json
import os
from typing import Optional, Dict, Any
from datetime import timedelta


class RedisCacheService:
    """
    Servicio para manejar el caché de datos con Redis
    """

    def __init__(self):
        """
        Inicializa la conexión a Redis
        """
        # Obtiene la URL de Redis desde variables de entorno
        # Por defecto: redis://localhost:6379 (desarrollo local)
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')

        try:
            self.client = redis.from_url(
                redis_url,
                decode_responses=True,  # Convierte bytes a strings automáticamente
                socket_connect_timeout=5,
                socket_timeout=5
            )
            # Prueba la conexión
            self.client.ping()
            print(f"✅ Conectado a Redis: {redis_url}")
        except redis.ConnectionError as e:
            print(f"⚠️ Error conectando a Redis: {e}")
            print("⚠️ El caché no estará disponible")
            self.client = None

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene un valor del caché

        Args:
            key: Clave del caché (ej: "sunat:ruc:20123456789")

        Returns:
            Diccionario con los datos o None si no existe
        """
        if not self.client:
            return None

        try:
            data = self.client.get(key)
            if data:
                print(f"✅ Cache HIT: {key}")
                return json.loads(data)
            else:
                print(f"❌ Cache MISS: {key}")
                return None
        except Exception as e:
            print(f"⚠️ Error obteniendo del caché: {e}")
            return None

    def set(
        self,
        key: str,
        value: Dict[str, Any],
        ttl_seconds: int = 604800  # 7 días por defecto
    ) -> bool:
        """
        Guarda un valor en el caché con tiempo de expiración

        Args:
            key: Clave del caché
            value: Diccionario con los datos a guardar
            ttl_seconds: Tiempo de vida en segundos (default: 7 días)

        Returns:
            True si se guardó correctamente, False si hubo error
        """
        if not self.client:
            return False

        try:
            serialized_value = json.dumps(value, ensure_ascii=False)
            self.client.setex(key, ttl_seconds, serialized_value)
            print(f"💾 Guardado en caché: {key} (TTL: {ttl_seconds}s)")
            return True
        except Exception as e:
            print(f"⚠️ Error guardando en caché: {e}")
            return False

    def delete(self, key: str) -> bool:
        """
        Elimina un valor del caché

        Args:
            key: Clave del caché a eliminar

        Returns:
            True si se eliminó, False si hubo error
        """
        if not self.client:
            return False

        try:
            self.client.delete(key)
            print(f"🗑️ Eliminado del caché: {key}")
            return True
        except Exception as e:
            print(f"⚠️ Error eliminando del caché: {e}")
            return False

    def clear_pattern(self, pattern: str) -> int:
        """
        Elimina todas las claves que coincidan con un patrón

        Args:
            pattern: Patrón de búsqueda (ej: "sunat:ruc:*")

        Returns:
            Número de claves eliminadas
        """
        if not self.client:
            return 0

        try:
            keys = self.client.keys(pattern)
            if keys:
                deleted = self.client.delete(*keys)
                print(f"🗑️ Eliminadas {deleted} claves con patrón: {pattern}")
                return deleted
            return 0
        except Exception as e:
            print(f"⚠️ Error limpiando caché: {e}")
            return 0

    def health_check(self) -> bool:
        """
        Verifica si Redis está funcionando

        Returns:
            True si Redis responde, False si no
        """
        if not self.client:
            return False

        try:
            return self.client.ping()
        except Exception:
            return False


# Singleton: Una única instancia para toda la aplicación
_cache_service = None

def get_cache_service() -> RedisCacheService:
    """
    Obtiene la instancia única del servicio de caché
    """
    global _cache_service
    if _cache_service is None:
        _cache_service = RedisCacheService()
    return _cache_service
```

#### 💡 Explicación:

- **`get(key)`**: Busca un valor en Redis. Si existe, lo devuelve; si no, devuelve `None`
- **`set(key, value, ttl_seconds)`**: Guarda un valor en Redis con un tiempo de expiración
- **`delete(key)`**: Elimina una clave específica
- **`clear_pattern(pattern)`**: Elimina múltiples claves (ej: todos los RUCs)
- **`health_check()`**: Verifica que Redis esté funcionando
- **Singleton**: Solo se crea una conexión a Redis para toda la aplicación

---

### **PASO 4: Modificar el Use Case** 💻

Ahora integramos Redis en la lógica de consulta de RUC.

#### 4.1 Editar `app/core/use_cases/integracion_sunat/integracion_sunat_uc.py`

```python
"""
Caso de uso para la integración con SUNAT
"""
from typing import Dict
from app.adapters.outbound.external_services.sunat.sunat_scraper import SunatScraper
from app.infrastructure.cache.redis_cache import get_cache_service
import re
import asyncio
from selenium.common.exceptions import TimeoutException


class IntegracionSunatUC:
    """
    Caso de uso para consultar información de RUC en SUNAT
    """

    def __init__(self, sunat_scraper: SunatScraper):
        self.sunat_scraper = sunat_scraper
        self.cache_service = get_cache_service()  # ← NUEVO: Servicio de caché
        self.cache_ttl = 604800  # 7 días en segundos

    async def obtener_ruc(self, ruc: str, max_intentos: int = 3) -> Dict:
        """
        Obtiene información de un RUC desde SUNAT con caché

        Args:
            ruc (str): Número de RUC a consultar
            max_intentos (int): Número máximo de intentos

        Returns:
            Dict: Información del RUC o error
        """
        # Validar formato de RUC
        if not self._validar_ruc(ruc):
            return {
                "message": "Error al consultar RUC",
                "detail": "El formato del RUC no es válido. Debe tener 11 dígitos.",
                "ruc": ruc
            }

        # ========================================
        # 1. BUSCAR EN CACHÉ PRIMERO
        # ========================================
        cache_key = f"sunat:ruc:{ruc}"
        cached_data = self.cache_service.get(cache_key)

        if cached_data:
            print(f"✅ Retornando datos desde caché para RUC: {ruc}")
            return cached_data

        # ========================================
        # 2. NO ESTÁ EN CACHÉ → HACER SCRAPING
        # ========================================
        print(f"❌ RUC {ruc} no encontrado en caché, consultando SUNAT...")

        ultimo_error = None

        for intento in range(1, max_intentos + 1):
            try:
                print(f"Intento {intento}/{max_intentos} para RUC {ruc}")

                # Realizar consulta en SUNAT con modo rápido por defecto
                resultado = self.sunat_scraper.consultar_ruc(ruc, modo_rapido=True)

                # Verificar si hubo error en la consulta
                if "error" in resultado and resultado["razonSocial"] == "Error en consulta":
                    ultimo_error = resultado.get('error', 'Error desconocido')

                    # Verificar si es un error de timeout para recrear el driver
                    if "timeout" in ultimo_error.lower() or "timed out" in ultimo_error.lower():
                        print(f"Timeout detectado, recreando WebDriver...")
                        self.sunat_scraper.driver_manager.cleanup()
                        await asyncio.sleep(2)

                    if intento < max_intentos:
                        print(f"Error en intento {intento}, reintentando...")
                        continue
                    else:
                        return {
                            "message": "Error al consultar RUC",
                            "detail": f"No se pudo obtener información del RUC {ruc} después de {max_intentos} intentos. Último error: {ultimo_error}",
                            "ruc": ruc
                        }

                # ========================================
                # 3. CONSULTA EXITOSA → GUARDAR EN CACHÉ
                # ========================================
                print(f"✅ Consulta exitosa en intento {intento}")

                # Guardar en Redis con expiración de 7 días
                self.cache_service.set(cache_key, resultado, self.cache_ttl)

                return resultado

            except TimeoutException as e:
                ultimo_error = f"Timeout del WebDriver: {str(e)}"
                print(f"Timeout en intento {intento}: {ultimo_error}")

                # Para errores de timeout, limpiar el driver y reintentar
                print("Recreando WebDriver debido a timeout...")
                self.sunat_scraper.driver_manager.cleanup()

                if intento < max_intentos:
                    print(f"Reintentando en 3 segundos...")
                    await asyncio.sleep(3)
                    continue

            except Exception as e:
                ultimo_error = str(e)
                print(f"Error en intento {intento}: {ultimo_error}")

                # Verificar si el error contiene indicios de timeout
                if "timeout" in ultimo_error.lower() or "timed out" in ultimo_error.lower():
                    print("Error relacionado con timeout, recreando WebDriver...")
                    self.sunat_scraper.driver_manager.cleanup()
                    await asyncio.sleep(2)
                elif "renderer" in ultimo_error.lower():
                    print("Error del renderer, recreando WebDriver...")
                    self.sunat_scraper.driver_manager.cleanup()
                    await asyncio.sleep(2)

                if intento < max_intentos:
                    print(f"Reintentando en 2 segundos...")
                    await asyncio.sleep(2)
                    continue

        # Si llegamos aquí, todos los intentos fallaron
        return {
            "message": "Error al consultar RUC",
            "detail": f"Error interno al consultar el RUC {ruc} después de {max_intentos} intentos. Último error: {ultimo_error}",
            "ruc": ruc
        }

    def _validar_ruc(self, ruc: str) -> bool:
        """
        Valida el formato del RUC

        Args:
            ruc (str): Número de RUC a validar

        Returns:
            bool: True si el formato es válido
        """
        # El RUC debe tener exactamente 11 dígitos
        if not ruc or len(ruc) != 11:
            return False

        # Debe contener solo números
        if not ruc.isdigit():
            return False

        return True
```

---

### **PASO 5: Ejecutar con Docker Compose** 🚀

#### 5.1 Levantar los servicios

Abre una terminal en la raíz del proyecto y ejecuta:

```bash
# Construir e iniciar todos los servicios
docker-compose up --build
```

#### 5.2 Comandos útiles

```bash
# Iniciar en segundo plano (detached mode)
docker-compose up -d

# Ver logs en tiempo real
docker-compose logs -f

# Ver solo logs de Redis
docker-compose logs -f redis

# Ver solo logs del backend
docker-compose logs -f backend

# Detener todos los servicios
docker-compose down

# Detener y eliminar volúmenes (borra datos de Redis)
docker-compose down -v

# Reiniciar un servicio específico
docker-compose restart backend
```

#### 5.3 Verificar que funcione

1. **Probar el endpoint:**
   ```bash
   curl http://localhost:8000/obtener-ruc/20123456789
   ```

2. **Primera consulta**: Tardará 10-30 segundos (consulta SUNAT)
3. **Segunda consulta del mismo RUC**: Tardará < 100ms (desde caché) ✅

#### 5.4 Monitorear Redis

```bash
# Conectarse al contenedor de Redis
docker exec -it crm_redis redis-cli

# Dentro de Redis, ejecutar:
KEYS *                    # Ver todas las claves
GET sunat:ruc:20123456789 # Ver datos de un RUC específico
TTL sunat:ruc:20123456789 # Ver tiempo restante antes de expirar
FLUSHALL                  # Borrar todo el caché (cuidado!)
```

---

## 🧪 Testing y Validación

### Prueba 1: Cache Miss (primera vez)
```bash
curl -w "\nTiempo: %{time_total}s\n" http://localhost:8000/obtener-ruc/20123456789
```
**Resultado esperado**: 10-30 segundos

### Prueba 2: Cache Hit (segunda vez, mismo RUC)
```bash
curl -w "\nTiempo: %{time_total}s\n" http://localhost:8000/obtener-ruc/20123456789
```
**Resultado esperado**: < 0.1 segundos ⚡

---

## 🔧 Configuración de Producción (Railway/Render)

### Para Railway:

1. **Agregar Redis como servicio:**
   - En Railway, ve a tu proyecto
   - Click en "New" → "Database" → "Redis"
   - Railway creará una variable de entorno `REDIS_URL` automáticamente

2. **Tu backend la detectará automáticamente** porque usamos:
   ```python
   redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
   ```

### Para Render:

1. **Crear servicio Redis:**
   - Render ofrece Redis como add-on
   - Agregar a tu servicio web
   - Configurar variable `REDIS_URL`

---

## 📊 Monitoreo y Métricas

### Agregar endpoint de health check

```python
# En tu archivo principal de FastAPI
from app.infrastructure.cache.redis_cache import get_cache_service

@app.get("/health")
async def health_check():
    cache_service = get_cache_service()
    return {
        "status": "healthy",
        "redis": "connected" if cache_service.health_check() else "disconnected"
    }
```

---

## 🎯 Resumen de Beneficios

| Métrica | Antes | Después | Mejora |
|---------|-------|---------|--------|
| **Tiempo de respuesta (cache hit)** | 10-30s | < 100ms | **99% más rápido** |
| **Carga en SUNAT** | 100% | 10-20% | **80-90% reducción** |
| **Experiencia de usuario** | Muy lenta | Instantánea | ⭐⭐⭐⭐⭐ |
| **Costo de infraestructura** | Alto | Bajo | 💰 Ahorro |

---

## ❓ FAQ (Preguntas Frecuentes)

### ¿Qué pasa si Redis falla?
El sistema sigue funcionando, solo que sin caché. Todas las consultas irán directamente a SUNAT.

### ¿Cuánto espacio ocupa Redis?
Muy poco. Cada RUC ocupa ~2KB. Para 10,000 RUCs: ~20MB.

### ¿Cuándo se eliminan los datos?
Automáticamente después de 7 días (configurable con `cache_ttl`).

### ¿Puedo invalidar el caché manualmente?
Sí, usando:
```python
cache_service.delete(f"sunat:ruc:{ruc}")
```

### ¿Funciona en desarrollo local sin Docker?
Sí, instala Redis localmente:
```bash
# Windows (con Chocolatey)
choco install redis-64

# Mac
brew install redis

# Linux
sudo apt-get install redis-server
```

---

## 🎓 Conclusión

¡Felicidades! Has implementado un sistema de caché profesional con Redis. Ahora tu aplicación:

✅ Es **99% más rápida** para consultas repetidas
✅ Reduce la carga en SUNAT y tu servidor
✅ Mejora la experiencia del usuario drásticamente
✅ Está lista para escalar a miles de usuarios

**Próximos pasos recomendados:**
1. Monitorear el cache hit rate
2. Ajustar TTL según necesidades del negocio
3. Considerar migrar de Selenium a Requests (Fase 2)