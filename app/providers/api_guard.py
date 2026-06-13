def require_explicit_execute(execute: bool) -> None:
    if not execute:
        print("Modo dry-run: no se consumieron requests de API. Para ejecutar llamadas reales usa --execute.")


def assert_api_allowed(execute: bool) -> None:
    if not execute:
        raise RuntimeError(
            "Llamada API bloqueada: se requiere autorizacion explicita con --execute."
        )

