import os


class Settings:
    evolution_api_url: str = os.getenv("EVOLUTION_API_URL", "http://evolution-api:8080")
    evolution_api_key: str = os.getenv("EVOLUTION_API_KEY", "")
    evolution_instance: str = os.getenv("EVOLUTION_INSTANCE", "pskloud-prospector")

    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")

    handoff_phone: str = os.getenv("HANDOFF_PHONE", "")

    max_daily_outbound: int = int(os.getenv("MAX_DAILY_OUTBOUND", "50"))
    min_delay_seconds: int = int(os.getenv("MIN_DELAY_SECONDS", "60"))
    max_delay_seconds: int = int(os.getenv("MAX_DELAY_SECONDS", "120"))
    typing_delay_min_ms: int = int(os.getenv("TYPING_DELAY_MIN_MS", "3000"))
    typing_delay_max_ms: int = int(os.getenv("TYPING_DELAY_MAX_MS", "5000"))

    hour_start: int = int(os.getenv("HOUR_START", "8"))
    hour_end: int = int(os.getenv("HOUR_END", "16"))
    work_days: list[int] = [int(d.strip()) for d in os.getenv("WORK_DAYS", "0,1,2,3,4").split(",")]

    msg_saludo: str = os.getenv(
        "MSG_SALUDO",
        "Buenos dias, senores de {nombre_empresa}, un gusto saludarles.",
    )
    msg_calificacion: str = os.getenv(
        "MSG_CALIFICACION",
        "Queria consultarles brevemente: actualmente disponen de un software administrativo, "
        "contable y de control de inventario/POS que cumpla con las exigencias de ley?",
    )
    msg_presentacion: str = os.getenv(
        "MSG_PRESENTACION",
        "Pertenezco a la casa Premium-Soft creadora del software administrativo y contable "
        "disenado para adaptarse a todas las normativas de ley y facturacion electronica. "
        "Si tienes un espacio de tiempo esta semana, podemos agendar una llamada o videollamada "
        "para una demostracion en vivo de la suite y conversar sobre como podemos apoyarte "
        "con la migracion y nuestros planes flexibles.",
    )

    max_per_country_daily: int = int(os.getenv("MAX_PER_COUNTRY_DAILY", "25"))

    prospect_active_hours: int = int(os.getenv("PROSPECT_ACTIVE_HOURS", "24"))

    media_base_url: str = os.getenv("MEDIA_BASE_URL", "http://prospeccion-pskloud-openclaw-1:9000")

    data_dir: str = "/app/data"
    queue_file: str = "/app/data/leads_para_enviar.json"
    conversations_db: str = "/app/data/conversaciones.db"
    country_counts_file: str = "/app/data/envios_por_pais.json"
    daily_summary_file: str = "/app/data/resumen_diario.json"


settings = Settings()
