# Текущий статус

Обновлено: 2026-06-10 MSK

## Правило работы

Перед изменениями читать `docs/STATUS.md` и `docs/NEXT_STEPS.md`. Архитектурные
решения синхронно отражать в `README.md` и `README.ru.md`. После изменений
обновлять этот файл.

## Репозиторий

- локально: `/Users/kir/code/ArgoAWXk8sDVPdemo`;
- GitHub: `kirka1206/ArgoAWXk8sDVPdemo`;
- Gitea: `practicum/practicum-demo`;
- checkpoint до документационного коммита:
  `99e48b5a1548dc03dda31e85573d56a1bb9ac2cb`;
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

Рабочие Deployment платформы Ready: Gitea, все компоненты Argo CD, AWX
Operator, AWX web/task, request controller и self-service portal. Deployment
DexAuthenticator имеет состояние `2/2`.

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
- Alice успешно вошла через Dex и видит только профили `app-only` и
  `app-with-vm`;
- в portal добавлена кнопка `Выйти`, использующая созданный
  `DexAuthenticator` endpoint `/logout`;
- первая заявка Alice выявила, что DKP Dex передаёт технический идентификатор в
  `X-Auth-Request-User`; controller отклонил её с `owner is not approved`;
- portal исправлен: owner определяется по allowlist e-mail и разрешённой группе,
  Environment ID нормализуется в lowercase, UI показывает причину отказа;
- progress UX добавлен: пользовательские статусы `В работе`, `В очереди`,
  `Готово`, `Ошибка`, текущий этап и polling каждые 5 секунд;
- повторная отправка блокируется до terminal state, ошибка связи не останавливает
  последующие проверки статуса;
- выявлен дефект профиля `app-with-postgres-vm`: AWX job `70` завершался
  `failed`, потому что Alpine 3.23 не содержит пакет `postgresql15`;
- playbook исправлен: выбирает самый новый доступный `postgresqlNN`;
- controller исправлен: после трёх failed AWX attempts выставляет `Error` с
  причиной вместо бесконечного `Provisioning`;
- исправление проверено на исходной заявке Marina
  `practicum-env-marina-feature-10d265`: повторный AWX job `73` завершился
  `successful` за `43.5` секунды, итоговый status заявки — `Ready`;
- request controller: Ready;
- в Gitea создан repository push webhook на внутренний endpoint Argo CD;
- Gitea webhook allowlist ограничен точным Service DNS
  `argocd-server.practicum-tks.svc.cluster.local`;
- test delivery принят Argo CD: в логе `argocd-server` зафиксирован push event
  репозитория `practicum/practicum-demo`;
- Application переведён на canonical Gitea URL из webhook payload;
- только `argocd-repo-server` получил host alias
  `gitea-practicum.d8case.ru -> 192.168.2.31`; общекластерный DNS не изменялся;
- реальный push проверен: Argo CD увидел новый revision за `9` секунд без
  ручного `Sync` или `Refresh`;
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

Окружение `practicum-env-alice-feature-019354` также штатно прошло TTL:

- request перенесён из `requests/` в `archive/`;
- generated-каталог удалён из desired state;
- status: `Cleaned`;
- app, Service, Ingress, VirtualDisk и VirtualMachine удалены Argo CD prune;
- namespace `practicum-tks` и платформенные компоненты сохранены.

Текущее состояние self-service:

- активных EnvironmentRequest: `0`;
- активных generated environments: `0`;
- работающих tenant VM: `0`;
- builder VM: `2`, обе `Stopped`;
- active image: `practicum-alpine-golden-3-23-v2`.

Отклонённая заявка с некорректным Dex owner удалена из активной очереди.
Её status оставлен в Git как диагностический аудит.

Текущее Web-окружение Alice:

- ID: `practicum-env-alice-feature-537020`;
- профиль: `app-with-vm`;
- приложение: `1/1`, Ingress `192.168.2.31`;
- приложение опубликовано по HTTP; portal исправлен, чтобы не показывать
  несуществующий HTTPS для tenant Ingress без TLS;
- VM: `Running`, `10.66.0.32`, `AgentReady=True`;
- SSH через `d8 v ssh` и локальный ключ проверен;
- AWX job `59` запущен автоматически и завершён `successful`.
- Git commit в status восстановлен: `507855ee9542e9a8b1c93b3b462c623429e1a32f`.

Второе Web-окружение Alice `practicum-env-alice-feature-fef235` имеет профиль
`app-only` и штатно прошло TTL cleanup; виртуальная машина для него не
создавалась. Окружение `practicum-env-alice-feature-537020` также очищено по
TTL. Для выполнения сценария VM drift нужно создать новое временное окружение
профиля `app-with-vm`.

## Проверки

- Python syntax: пройдена;
- shell syntax: пройдена;
- Kustomize build: пройдена;
- server-side dry-run: пройден;
- Argo CD: `Synced/Healthy`;
- golden image Git -> Argo CD -> DVP -> AWX -> publish: пройден;
- Web request -> Git -> controller -> Argo CD -> DVP -> AWX: пройден;
- TTL cleanup: пройден.

## Сценарии

Добавлен `scenarios/12-dvp-vm-drift-correction.md`:

- безопасный drift по CPU/RAM;
- различие между DVP operation и изменением desired state;
- self-heal Argo CD;
- controlled restart;
- опциональное удаление только VM с сохранением диска;
- ограничения AWX и рекомендации RBAC/admission policy.

Это стабильная точка продолжения: Application `Synced/Healthy`, временные
environment-ресурсы очищены, golden images и остановленные builder-диски
сохранены.

## Известные особенности

- Gitea controller пишет status/generated коммитами в `main`; перед локальным
  push нужно сначала получить эти коммиты. Force-push запрещён.
- DNS для practicum hostnames должен указывать на `192.168.2.31`; до появления
  DNS используются записи `/etc/hosts`.
- Self-signed сертификат portal требует доверия браузера либо замены issuer.
- ServiceAccount показываются с `0` token secrets — это штатное поведение новых
  Kubernetes, токены выдаются через projected service account volumes.
