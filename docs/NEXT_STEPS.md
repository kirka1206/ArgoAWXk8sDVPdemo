# Следующие шаги

## Приоритет 1. Подготовить стенд к повторному показу

1. Создать DNS-записи для `gitea-practicum.d8case.ru`,
   `argocd-practicum.d8case.ru`, `awx-practicum.d8case.ru` и
   `selfservice-practicum.d8case.ru` на `192.168.2.31`.
2. Заменить self-signed Certificate portal на доверенный issuer.
3. Alice проверена через реальный Dex UI: доступны только `app-only` и
   `app-with-vm`. Проверить Boris и Marina и соответствие их профилей группам.
4. После доставки кнопки `Выйти` проверить завершение Dex-сессии, повторный
   redirect и вход под другим пользователем.
5. Создать новое тестовое окружение через Web, дождаться `Ready`, после чего
   проверить корректный owner/Environment ID, переход
   `Submitted -> Provisioning -> Ready` и автоматический TTL cleanup.
6. Проверить PostgreSQL-профиль для версий `16`, `17`, `18` и выполнить
   показанную portal команду `d8 v ssh`.
7. Выполнить `scenarios/11-practicum-end-to-end.md`, не изменяя опубликованные
   golden image v1/v2.
8. Заменить временный `SuperAdmin` пользователя `practicum-tks@demo.local` на
   минимально необходимые права.

## Приоритет 2. Проверить роли и профили

1. Alice: проверить `app-only` и `app-with-vm`.
2. Boris: проверить `app-only` и `app-with-postgres-vm`.
3. Marina: проверить все три профиля.
4. Victor: проверить start/stop/restart, console/VNC, disks и snapshots.
5. Подтвердить `Forbidden` для Victor на Secrets, Deployments, RBAC и изменение
   VirtualImage/ClusterVirtualImage.
6. Подтвердить, что разработчики не могут создавать VM напрямую.
7. Провести `scenarios/12-dvp-vm-drift-correction.md` на временной VM и
   проверить кратковременный `OutOfSync`, self-heal и controlled restart.

## Приоритет 3. Усилить Git workflow

Repository webhook Gitea -> Argo CD настроен для немедленного refresh после
push. Периодический polling остаётся резервным механизмом.

1. Перевести automation с прямых commit в `main` на branch/PR.
2. Объединить generated-файлы и kustomization в один Git commit через Git tree
   API или отдельный Git worker.
3. Добавить CI-проверку схемы EnvironmentRequest, owner/group/profile/TTL и
   Kustomize render до merge.
4. Добавить защиту ветки `main` и обязательное review platform team.
5. Исключить status-коммиты, если semantic status не изменился.

## Приоритет 4. Production hardening

1. Удалить legacy demo-default `codex123` из старых локальных bootstrap
   артефактов и заменить его обязательной генерацией/передачей Secret.
2. Перенести runtime credentials в External Secrets/Vault.
3. Добавить Prometheus-метрики controller: queued, active, failed, cleanup.
4. Добавить retry/backoff status для временных ошибок Gitea/AWX.
5. Добавить NetworkPolicy для portal, controller, Gitea и AWX.
6. Добавить резервное копирование Gitea и AWX PostgreSQL/PVC.
7. Связать request commit, generated commit, Argo revision, AWX job и cleanup
   commit в едином audit trail.
8. Проверить quota exhaustion и очередь при настраиваемых лимитах
   `MAX_ACTIVE_ENVIRONMENTS=7`, `MAX_ACTIVE_VMS=7`.

## Приоритет 5. Golden image lifecycle

1. Описать выпуск v3 без изменения v1/v2.
2. Автоматизировать публикацию image только после успешной validation.
3. Добавить metadata: source URL/checksum, package list, build date, AWX job и
   Git revision.
4. Реализовать controlled promotion `candidate -> active`.
5. Проверить rollback `activeGoldenImage` с v2 на v1 отдельным Git-коммитом.
6. Решить, сохранять ли builder disks после демо; versioned VirtualImage
   удалять или изменять нельзя.

## Порядок безопасного продолжения

1. Проверить context `practicum-tks-api.d8case.ru`.
2. Проверить `practicum-demo` в состоянии `Synced/Healthy`.
3. Получить новые controller-коммиты из Gitea до локальных изменений.
4. Не использовать force-push.
5. Не удалять объекты без labels/prefix `practicum`.
6. После каждого этапа обновлять `docs/STATUS.md`, запускать проверки и
   отправлять изменения в GitHub и practicum Gitea.

## Полезные команды

```bash
kubectl get application -n practicum-tks practicum-demo
kubectl get vi,vd,vm -n practicum-tks -o wide
kubectl get deploy,svc,ingress -n practicum-tks
kubectl logs -n practicum-tks deploy/practicum-request-controller
kubectl get dexauthenticator,certificate -n practicum-tks
kubectl get deploy,svc,ingress,vd,vm -n practicum-tks \
  -l demo.practicum/environment
git fetch practicum-gitea main
git status
```
