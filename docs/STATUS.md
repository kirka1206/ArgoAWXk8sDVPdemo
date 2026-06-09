# Текущий статус

Обновлено: 2026-06-09 15:05 MSK

## Правило работы

Перед изменениями читать `docs/STATUS.md` и `docs/NEXT_STEPS.md`. Архитектурные
решения синхронно отражать в `README.md` и `README.ru.md`. После изменений
обновлять этот файл.

## Репозиторий

- локально: `/Users/kir/code/ArgoAWXk8sDVPdemo`;
- GitHub: `kirka1206/ArgoAWXk8sDVPdemo`;
- Gitea: `practicum/practicum-demo`;
- remote `practicum-gitea` не содержит пароль в URL;
- старые remote `dkp-gitea` и стенд `d8.kir.lab` не изменялись.

## Новый стенд

- context: `practicum-tks-api.d8case.ru`;
- DKP Project и namespace: `practicum-tks`;
- ingress IP: `192.168.2.31`;
- StorageClass: `replicated`;
- VirtualMachineClass: `generic`;
- квота: `4 CPU`, `8Gi RAM`, `30Gi storage`.

Платформа Ready:

- Gitea `1.24.6`;
- Argo CD `3.4.2`;
- AWX Operator `2.19.1`;
- AWX `24.6.1`;
- Application `practicum-demo`: `Synced/Healthy`.

## Пользователи и RBAC

- Alice: `practicum-payments-devs`, app-only и app-with-vm;
- Boris: `practicum-analytics-devs`, app-only и app-with-postgres-vm;
- Marina: `practicum-qa-devs`, все self-service профили;
- Victor: `practicum-vm-operators`, ограниченное управление DVP VM/дисками;
- Gitea bot: `practicum-portal-bot`;
- AWX account: `practicum-automation`;
- ServiceAccount: `practicum-self-service-portal`;
- ServiceAccount: `practicum-request-controller`.

Пароли хранятся только в ignored-файле `local/practicum-demo-users.env`.

## Golden images

- source `practicum-alpine-base-3-23-v1`: Ready;
- immutable `practicum-alpine-golden-3-23-v1`: Ready;
- immutable `practicum-alpine-golden-3-23-v2`: Ready;
- active image: v2;
- AWX workflow job `40`: successful;
- оба builder VM остановлены, ресурсы минимальные.

## Self-service

- portal: `https://selfservice-practicum.d8case.ru`;
- Certificate: Ready;
- DexAuthenticator: создан;
- request controller: Ready;
- один namespace для всех environments: `practicum-tks`;
- лимиты: 3 активных environment, 2 VM;
- controller не выполняет прямой `kubectl delete`;
- AWX стартует после guest readiness, максимум 3 попытки.

Проверенное окружение:

- ID: `practicum-env-alice-feature-019354`;
- app: `1/1`;
- VM: Running, `512Mi`, `1 core / 5%`, disk `768Mi`;
- image: `practicum-alpine-golden-3-23-v2`;
- DVP AgentReady: True;
- AWX job `55`: successful.

TTL проверен на `practicum-env-alice-demo-968c7a`: request архивирован, status
`Cleaned`, Argo CD prune удалил только app/ingress/VM/disk этой заявки.

## Проверки

- Python syntax: пройдена;
- shell syntax: пройдена;
- Kustomize build: пройдена;
- server-side dry-run: пройден;
- Argo CD: `Synced/Healthy`;
- golden image Git -> Argo CD -> DVP -> AWX -> publish: пройден;
- Web request -> Git -> controller -> Argo CD -> DVP -> AWX: пройден;
- TTL cleanup: пройден.

## Известные особенности

- Gitea controller пишет status/generated коммитами в `main`; перед локальным
  push нужно сначала получить эти коммиты. Force-push запрещён.
- DNS для practicum hostnames должен указывать на `192.168.2.31`; до появления
  DNS используются записи `/etc/hosts`.
- Self-signed сертификат portal требует доверия браузера либо замены issuer.
