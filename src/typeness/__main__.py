import argparse

from typeness.main import main


def cli():
    """CLI entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        prog="typeness",
        description="Local voice input tool — speech to structured text",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="save each recording as WAV + JSON to the debug/ directory",
    )
    parser.add_argument(
        "--install-login-item",
        action="store_true",
        help="install Typeness as a macOS login item (auto-start at login)",
    )
    parser.add_argument(
        "--uninstall-login-item",
        action="store_true",
        help="remove the Typeness macOS login item",
    )
    args = parser.parse_args()

    if args.install_login_item:
        from typeness.login_item import install
        install()
        return

    if args.uninstall_login_item:
        from typeness.login_item import uninstall
        uninstall()
        return

    main(debug=args.debug)


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    try:
        cli()
    except KeyboardInterrupt:
        print("\nBye!")
