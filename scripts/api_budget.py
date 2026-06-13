from __future__ import annotations

from app.providers.rate_limiter import get_budget_summary


def main() -> None:
    summary = get_budget_summary()
    print("PRESUPUESTO API - MUNDIAL 2026")
    print(f"Perfil API seleccionado: {summary['api_profile']}")
    print(f"API key configurada: {'si' if summary['api_key_configured'] else 'no'}")
    print(f"Limite diario: {summary['daily_limit']}")
    print(f"Requests usados hoy: {summary['used_today']}")
    print(f"Requests restantes hoy: {summary['remaining_today']}")
    print(f"Limite por minuto: {summary['per_minute_limit']}")
    print(f"Segundos minimos entre requests: {summary['min_seconds_between_requests']}")
    print(f"Ultimo request: {summary['last_request_timestamp'] or '-'}")
    print(f"Ledger: {summary['ledger_path']}")
    print(f"Cache habilitado: {'si' if summary['cache_enabled'] else 'no'}")
    print("Requests recientes:")
    for item in summary["recent_requests"]:
        print(f"- {item.get('timestamp')} {item.get('endpoint')} {item.get('status')}")
    if not summary["recent_requests"]:
        print("- Sin requests registrados")
    print("Este comando no consume API.")


if __name__ == "__main__":
    main()
