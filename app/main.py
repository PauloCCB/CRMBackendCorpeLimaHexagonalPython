"""
FastAPI Application with Hexagonal Architecture
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.adapters.inbound.api.routers import users, products, orders, health, upload_xml, generar_oc, dolar
from app.config.settings import get_settings

settings = get_settings()

def create_app() -> FastAPI:
    """
    Crear y configurar la aplicación FastAPI
    """
    app = FastAPI(
        title="CRM Backend - Hexagonal Architecture",
        description="Sistema CRM implementado con arquitectura hexagonal",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )
    allowed_origins=settings.cors_origins.split(",")  if settings.cors_origins else [] 
    # Configurar CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,  # En producción, especificar dominios exactos
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Registrar rutas
    app.include_router(health.router, prefix="/api", tags=["Health"])
    app.include_router(users.router, prefix="/api", tags=["Users"])
    app.include_router(products.router, prefix="/api", tags=["Products"])
    app.include_router(orders.router, prefix="/api", tags=["Orders"])
    app.include_router(upload_xml.router, prefix="/api", tags=["Upload XML"])
    app.include_router(generar_oc.router, prefix="/api", tags=["Generar OC"])
    app.include_router(dolar.router, prefix="/api", tags=["Dolar"])
    return app

# Crear la instancia de la aplicación
app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    ) 