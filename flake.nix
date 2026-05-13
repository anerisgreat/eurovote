{
  description = "Eurovision voting web app";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      supportedSystems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];

      forEachSystem = f: nixpkgs.lib.genAttrs supportedSystems (system:
        let pkgs = nixpkgs.legacyPackages.${system}; in f pkgs
      );

      pythonEnv = pkgs: pkgs.python3.withPackages (ps: [
        ps.django
        ps.pyyaml
      ]);

      # Source package: the app tree in the Nix store.
      # Used by the NixOS module so homey can reference the source without
      # having it checked out on the target machine.
      mkPackage = pkgs: pkgs.stdenvNoCC.mkDerivation {
        name = "eurovote";
        src = ./.;
        installPhase = ''
          mkdir -p $out
          cp -r . $out/
        '';
      };

    in {
      packages = forEachSystem (pkgs: {
        default = mkPackage pkgs;
      });

      devShells = forEachSystem (pkgs: {
        default = pkgs.mkShell {
          buildInputs = [ (pythonEnv pkgs) pkgs.nixpkgs-fmt ];
          shellHook = ''
            echo "Eurovision Vote dev shell"
            echo ""
            echo "  Setup:   python manage.py migrate"
            echo "           python manage.py createsuperuser"
            echo "  Run:     python manage.py runserver"
          '';
        };
      });

      # `nix run` — dev convenience: run from the current checkout directory.
      # For production use the NixOS module instead.
      apps = forEachSystem (pkgs: {
        default =
          let
            py = pythonEnv pkgs;
            runScript = pkgs.writeShellApplication {
              name = "eurovote";
              runtimeInputs = [ py ];
              text = ''
                repo_root="$(${pkgs.git}/bin/git -C "$(dirname "$0")" rev-parse --show-toplevel 2>/dev/null || echo ".")"
                cd "$repo_root"
                python manage.py migrate
                python manage.py runserver 0.0.0.0:8000
              '';
            };
          in {
            type = "app";
            program = "${runScript}/bin/eurovote";
          };
      });

      # nixosModules.default — import this from a NixOS flake (e.g. homey).
      # See README.md § "Integrating into a self-hosted NixOS environment".
      #
      # Admin access in production: all SSO-authenticated users are granted
      # is_staff + is_superuser by RemoteUserMiddleware. Authelia's group/policy
      # config is the real gate — protect /admin/* at the reverse proxy level.
      # No separate admin account creation is needed.
      nixosModules.default = { config, lib, pkgs, ... }:
        let
          cfg = config.services.eurovote;
          src = mkPackage pkgs;
          py  = pythonEnv pkgs;
          manage = "${py}/bin/python ${src}/manage.py";
        in {
          options.services.eurovote = {
            enable = lib.mkEnableOption "Eurovision voting web app";

            port = lib.mkOption {
              type    = lib.types.port;
              default = 8007;
              description = "localhost port the app listens on";
            };

            dataDir = lib.mkOption {
              type    = lib.types.path;
              default = "/var/lib/eurovote";
              description = "Directory for db.sqlite3 and other runtime state";
            };

            secretKeyFile = lib.mkOption {
              type        = lib.types.path;
              description = "Path to file containing DJANGO_SECRET_KEY (e.g. a sops secret)";
            };

            allowedHosts = lib.mkOption {
              type    = lib.types.str;
              default = "localhost 127.0.0.1";
              description = "Space-separated ALLOWED_HOSTS value";
            };
          };

          config = lib.mkIf cfg.enable {
            systemd.services.eurovote = {
              description = "Eurovision Vote Django app";
              wantedBy    = [ "multi-user.target" ];
              after       = [ "network.target" ];

              environment = {
                DJANGO_DEBUG   = "false";
                ALLOWED_HOSTS  = cfg.allowedHosts;
                DJANGO_DB_PATH = "${cfg.dataDir}/db.sqlite3";
              };

              serviceConfig = {
                Type           = "simple";
                DynamicUser    = true;
                StateDirectory = "eurovote";

                # Write ephemeral env file with secrets; never lands in the Nix store.
                ExecStartPre = [
                  (pkgs.writeShellScript "eurovote-setup" ''
                    set -euo pipefail
                    SECRET_KEY=$(cat ${cfg.secretKeyFile})

                    printf '%s\n' \
                      "DJANGO_SECRET_KEY=$SECRET_KEY" \
                      > /run/eurovote-secrets.env
                    chmod 600 /run/eurovote-secrets.env

                    DJANGO_SECRET_KEY="$SECRET_KEY" \
                    DJANGO_DB_PATH="${cfg.dataDir}/db.sqlite3" \
                    DJANGO_DEBUG=false \
                    ALLOWED_HOSTS="${cfg.allowedHosts}" \
                      ${manage} migrate --no-input
                  '')
                ];

                ExecStart = pkgs.writeShellScript "eurovote-start" ''
                  set -euo pipefail
                  source /run/eurovote-secrets.env
                  exec ${manage} runserver 127.0.0.1:${toString cfg.port}
                '';

                ExecStopPost = pkgs.writeShellScript "eurovote-cleanup" ''
                  rm -f /run/eurovote-secrets.env
                '';
              };
            };
          };
        };
    };
}
