# Демонстрационные сценарии стенда d8case.ru

Этот каталог является актуальным комплектом инструкций для стенда:

```text
DKP Project: practicum-tks
Namespace:   practicum-tks
Context:     practicum-tks-api.d8case.ru
```

Материалы в корне `scenarios/` сохраняются как история предыдущих стендов.
Команды с `demo-prod`, `d8.kir.lab`, `demo-platform`, `ansible-os-pods`,
`golden-builder-vm` и `postgres-vm` на новом стенде выполнять не следует.

## Актуальные адреса

| Компонент | Адрес |
|---|---|
| Gitea | `http://gitea-practicum.d8case.ru` |
| Argo CD | `http://argocd-practicum.d8case.ru` |
| AWX | `http://awx-practicum.d8case.ru` |
| Портал разработчика | `https://selfservice-practicum.d8case.ru` |
| Портал Victor | `https://vm-admin-practicum.d8case.ru` |

Для временного разрешения имён:

```text
192.168.2.31 gitea-practicum.d8case.ru
192.168.2.31 argocd-practicum.d8case.ru
192.168.2.31 awx-practicum.d8case.ru
192.168.2.31 selfservice-practicum.d8case.ru
192.168.2.31 vm-admin-practicum.d8case.ru
```

Tenant Ingress имеет динамическое имя:

```text
192.168.2.31 <environment-id>.d8case.ru
```

## Порядок показа

1. [Подготовка демонстратора](00-preflight.md).
2. [Архитектура и границы ответственности](01-architecture-tour.md).
3. [Управление golden images](02-golden-image-lifecycle.md).
4. [Self-service через Git и YAML](03-git-environment-request.md).
5. [Self-service через Web](04-web-self-service.md).
6. [Административное управление Victor](05-victor-lifecycle.md).
7. [Drift correction DVP VM](06-vm-drift-correction.md).
8. [Cleanup и troubleshooting](07-cleanup-and-troubleshooting.md).

Полный показ занимает 45-60 минут. Для короткого показа используйте сценарии
`01`, `02`, `04` и `05`.

## Правила безопасности

- Не удалять namespace или DKP Project `practicum-tks`.
- Не изменять и не удалять опубликованные golden images `v1` и `v2`.
- Не выполнять `kubectl delete` для tenant environments в штатном сценарии.
- Lifecycle выполнять через пользовательский или административный портал.
- Ручной drift показывать только на временной VM, которую можно пересоздать.
- Перед изменением Git выполнить `git fetch practicum-gitea main`.
- Никогда не использовать force-push: controller пишет status в `main`.

## Соответствие старым сценариям

| Старый сценарий | Статус на d8case.ru | Актуальная замена |
|---|---|---|
| 01 Initial Deploy | Не применяется отдельно | `00`, `01` |
| 02 Scale Application | Не является основным сценарием | Не показывать |
| 03 Drift Correction | Заменён DVP-вариантом | `06` |
| 04 VM Resize | Входит в drift/GitOps объяснение | `06` |
| 05 AWX Post-Config | Автоматизирован controller | `03`, `04` |
| 06 Broken Release | Не входит в текущий показ | Не показывать |
| 07 Self-Service Tenant | Namespace не создаётся | `03`, `04` |
| 08 Golden Image | Полностью заменён | `02` |
| 09 Git Environment Request | Полностью заменён | `03` |
| 10 Self-Service Portal | Полностью заменён | `04` |
| 11 Practicum End-to-End | Разделён на понятные этапы | `01`-`05` |
| 12 DVP VM Drift | Актуализирован | `06` |
| 13 Manual Lifecycle | Актуализирован | `05` |

