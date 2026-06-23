# Текущий статус

Обновлено: 2026-06-23 MSK

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
- active image: v1; временно переключён для live-демонстрации 2026-06-23,
  образ v2 остаётся `Ready` и должен быть возвращён как активный после показа;
- AWX workflow job `40`: successful;
- оба builder VM остановлены, ресурсы минимальные.
- сценарий `scenarios/d8case/02-golden-image-lifecycle.md` дополнен
  примерами альтернативных source images для демо: Alpine 3.23 v2,
  Alpine 3.22 v1 и Ubuntu 24.04 как более тяжёлый архитектурный пример;
- в сценарии явно описан rollback через отдельный Git commit,
  переключающий `activeGoldenImage` обратно на предыдущую версию; rollback
  влияет только на новые VM и не изменяет уже provisioned VirtualDisk.
- в актуальный сценарий добавлена полная PlantUML sequence-диаграмма выпуска
  golden image: Git, Gitea webhook, Argo CD, Kubernetes, DVP, AWX, сервис
  обработки заявок и безопасный rollback.
- в архитектурный сценарий добавлена крупноблочная PlantUML-схема связей между
  Git, Argo CD, Kubernetes/DVP, AWX, Python-сервисом обработки заявок и VM.

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
- portal и request contract расширены выбором PostgreSQL `16`, `17` или `18`;
  controller валидирует allowlist и передаёт точный пакет в AWX;
- выявлено ограничение Git-сценария: текущий Python-сервис читает файлы
  `EnvironmentRequest` с расширением `.yaml` как JSON. Актуальный сценарий
  `scenarios/d8case/03-git-environment-request.md` требует JSON-содержимое
  и явно запрещает обычный YAML до доработки parser;
- итоговый status Git-сценария читается через `git fetch` и
  `git show FETCH_HEAD:...`, а не через `git pull --rebase`, чтобы
  незакоммиченные локальные файлы не блокировали проверку результата;
- для VM-профилей status и portal показывают пользователя `ansible`, SSH key
  authentication и готовую команду `d8 v ssh`; секреты в Git не добавляются;
- обработчик временной ошибки Gitea сохраняет AWX job, attempts и runtime-поля
  существующего status, чтобы следующий reconcile не запускал job повторно;
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
- лимиты вынесены в env request controller:
  `MAX_ACTIVE_ENVIRONMENTS=7`, `MAX_ACTIVE_VMS=7`;
- изменение лимитов проверено на заявке
  `practicum-env-marina-bugfix-39884b`: после rollout controller она
  автоматически вышла из `Queued/capacity-limit` в `Provisioning`;
- реализован GitOps lifecycle через `EnvironmentAction`: delete environment,
  delete VM+disk, start, stop и restart VM;
- пользовательский portal получил `Мои стенды`, `История` и двойное
  подтверждение удаления собственных ресурсов;
- добавлен отдельный Victor portal `vm-admin-practicum.d8case.ru`, доступный
  только `practicum-vm-operators`; причина административного действия
  обязательна;
- action/request/generated/kustomization обновляются атомарным Gitea
  `repoChangeFiles` commit,
  фактическое удаление выполняет Argo CD prune;
- controller не выполняет прямой `kubectl delete`;
- AWX стартует после guest readiness, максимум 3 попытки.

Live-приёмка lifecycle выполнена 2026-06-10:

- Victor portal пропускает только Victor с группой
  `practicum-vm-operators`; запрос с неверной группой получает `403`;
- пользовательский API не разрешает Alice удалить стенд Marina и возвращает
  `403`;
- `restart-vm` прошёл через Git action и versioned
  `VirtualMachineOperation`, после выполнения operation удалён из desired
  state, VM осталась `Running`;
- `delete-vm` для `practicum-env-marina-bugfix-3b1e0b` удалил VM и
  VirtualDisk через Argo CD prune, сохранил Deployment, Service и Ingress и
  преобразовал request в `app-only`;
- последующий `delete-environment` перевёл status через
  `DeletionRequested/Deleting` в `Cleaned`, архивировал request/action и
  удалил только app, Service и Ingress выбранного environment;
- Application `practicum-demo` после операций вернулся в
  `Synced/Healthy`;
- оба portal Deployment и request controller имеют `1/1 Ready`,
  Certificate административного portal — `Ready`;
- desktop и mobile layout проверены на отсутствие горизонтального
  переполнения; фильтры, меню и модальные подтверждения проверены в браузере.

UX пользовательского portal дополнительно улучшен:

- карточка `Мои стенды` показывает те же основные данные, что и результат
  создания: Environment ID, namespace, owner, профиль, PostgreSQL, TTL,
  приложение, URL, VM/IP, ресурсы, golden image, SSH, AWX и Git commit;
- кнопка `Обновить` использует `no-store`, показывает время и количество
  полученных стендов, а ошибки загрузки выводит непосредственно на вкладке;
- чтение status-файлов из Gitea выполняется ограниченным параллельным пулом
  вместо последовательных HTTP-запросов, поэтому время обновления не растёт
  линейно вместе с историей environments;
- активная вкладка читает status только для текущих requests и выполняющихся
  actions; накопленный архив запрашивается отдельно при открытии `Истории`;
- во время provisioning и lifecycle-операций список автоматически обновляется
  каждые 5 секунд и объясняет текущий этап controller/Argo CD/DVP;
- поле `Назначение` снабжено динамическим пояснением: сейчас оно влияет на
  Environment ID и аудит, а ресурсы определяются выбранным профилем.

Административный portal Victor исправлен после алерта `IngressResponses5xx`:

- причиной были последовательный полный обход Git status каждые 5 секунд,
  наложение запросов и периодические ошибки/таймауты Gitea;
- backend получил 15-секундный cache, блокировку единственного refresh,
  загрузку status одним архивом ветки Gitea и возврат последнего успешного
  snapshot при временной ошибке Gitea;
- frontend не запускает новый refresh поверх незавершённого, polling увеличен
  до 15 секунд, ошибки показываются без очистки последней таблицы;
- кнопки `Обзор`, `Стенды`, `Виртуальные машины`, `Операции` и `Аудит` теперь
  являются настоящими представлениями с отдельной фильтрацией;
- API и браузер используют `no-store`, а UI показывает время последнего
  успешного обновления.
- pod template содержит декларативную версию ConfigMap-кода, поэтому изменение
  административного portal вызывает GitOps rollout Deployment, а не оставляет
  старый Python-процесс после состояния `Synced`.

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
- Python и встроенный JavaScript lifecycle portal: пройдены;
- atomic Gitea `repoChangeFiles` commit: пройден;
- user ownership и Victor group authorization: пройдены;
- `restart-vm`, `delete-vm`, `delete-environment`: пройдены;
- desktop/mobile UI lifecycle portal: пройден.

## Сценарии

Добавлены сценарии:

- `scenarios/12-dvp-vm-drift-correction.md`: drift, self-heal и controlled
  restart;
- `scenarios/13-manual-environment-lifecycle.md`: пользовательское удаление
  собственных ресурсов и административные операции Victor через Git actions.

Для действующего стенда создан отдельный канонический комплект
`scenarios/d8case/`:

- preflight с проверкой context, Application, DVP и URL;
- архитектурный рассказ Git → controller → Argo CD → DVP → AWX;
- golden image lifecycle с актуальными `practicum-*` объектами;
- Git/YAML self-service с `EnvironmentRequest`;
- Web self-service через Dex;
- административный lifecycle Victor;
- drift correction tenant VM;
- cleanup и troubleshooting.

В комплекте отсутствуют команды `demo-prod`, домен `d8.kir.lab` и имена
объектов старого стенда. Корневые `scenarios/01-13` сохранены как исторические
варианты и явно отделены в README.

## PDF-документация

Сформирован навигационный PDF по проекту:

```text
output/pdf/ArgoAWXk8sDVPdemo-project-guide.pdf
```

Источник сборки:

```text
scripts/build_project_pdf.py
```

PDF включает README, паспорт `d8case.ru`, текущий статус, актуальные сценарии
`scenarios/d8case`, исторические сценарии `01-13` и вспомогательные документы
из `docs/`. В PDF есть оглавление, page numbers и bookmarks/outline для
навигации. Выполнена визуальная проверка рендера выбранных страниц через
PyMuPDF в `tmp/pdfs/project-guide-render/`.

PDF пересобран после проверки форматирования:

- fenced code blocks выводятся как код, без HTML-escape артефактов для
  кавычек и угловых скобок;
- Mermaid flowchart blocks преобразуются в читаемые PDF-диаграммы-цепочки, а
  не выводятся как сырой DSL;
- итоговый файл содержит `137` страниц и `69` bookmarks/outline entries;
- целевые страницы с архитектурной схемой и примером `EnvironmentRequest`
  визуально проверены через PyMuPDF.

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
