"""Create or reuse the deterministic, passwordless local demonstration workspace."""
from fastdps.bootstrap import ensure_demo, initialize


def main() -> None:
    initialize()
    user, organisation = ensure_demo()
    print(f"Demo workspace ready: {organisation['name']} ({user['email']})")
    print("Enable FASTDPS_ALLOW_TEST_AUTH=true and open /auth/test to use it.")


if __name__ == "__main__":
    main()
