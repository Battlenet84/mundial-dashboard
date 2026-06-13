from app.db.queries import get_api_budget_summary


def main() -> None:
    budget = get_api_budget_summary()
    total = 3
    print("PLAN CORE FETCH - MUNDIAL 2026")
    print("Coverage: 1 request estimado")
    print("Teams: 1 request estimado")
    print("Fixtures: 1 request estimado")
    print(f"Total estimado: {total}")
    print(f"Requests restantes hoy: {budget['remaining_today']}")
    print(f"Entra en presupuesto: {'si' if total <= budget['remaining_today'] else 'no'}")
    print("Este comando no consume API.")


if __name__ == "__main__":
    main()

