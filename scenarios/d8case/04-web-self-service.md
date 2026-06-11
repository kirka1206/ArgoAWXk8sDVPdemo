# 04. Self-service через Web

## Цель

Показать удобный интерфейс разработчика, который создаёт тот же
`EnvironmentRequest`, что и ручной Git-сценарий.

## Пользователи и профили

| Пользователь | Группа | Профили |
|---|---|---|
| Alice | `practicum-payments-devs` | app-only, app-with-vm |
| Boris | `practicum-analytics-devs` | app-only, app-with-postgres-vm |
| Marina | `practicum-qa-devs` | все профили |

Для полного показа используйте Marina:

```text
marina.volkova.practicum@demo.local
```

Пароль берётся из локального ignored-файла, не из Git.

## 1. Открыть портал

```text
https://selfservice-practicum.d8case.ru
```

Примите предупреждение self-signed certificate и войдите через Dex.

## 2. Объяснить поля

### Профиль стенда

Профиль определяет ресурсы:

- `Контейнерное приложение`: Deployment, Service, Ingress;
- `Приложение + Linux VM`: добавляются DVP disk/VM и AWX bootstrap;
- `Приложение + PostgreSQL VM`: добавляется выбранная версия PostgreSQL.

Пользователь не задаёт произвольные CPU/RAM/image.

### Назначение

Назначение:

- входит в Environment ID;
- сохраняется в Git и аудите;
- не меняет ресурсы профиля.

### TTL

TTL определяет автоматическое время жизни. После истечения controller меняет
desired state в Git, а Argo CD prune удаляет только ресурсы стенда.

## 3. Создать стенд

Для наиболее наглядного показа:

```text
Профиль: Приложение + PostgreSQL VM
PostgreSQL: 18
Назначение: Демонстрация
TTL: 4h
```

Нажмите `Отправить заявку`.

## 4. Читать прогресс

Portal обновляет status каждые 5 секунд. Объясняйте этапы:

1. `Submitted` — request записан в Gitea;
2. `Provisioning` — controller создал desired state;
3. Argo CD создаёт Deployment, Service, Ingress, disk и VM;
4. DVP запускает VM;
5. AWX выполняет post-config;
6. `Ready` — все проверки завершены.

## 5. Проверить результат

Portal должен показать:

- Environment ID;
- namespace `practicum-tks`;
- owner и profile;
- PostgreSQL version;
- TTL;
- приложение `ready 1/1`;
- URL;
- VM, IP, CPU/RAM/disk и image;
- AWX job/status;
- готовую команду `d8 v ssh`.

В терминале:

```bash
export ENV_ID=<скопировать-из-портала>

kubectl get deploy,svc,ingress,vd,vm -n practicum-tks \
  -l "demo.practicum/environment=${ENV_ID}" -o wide
```

## 6. Показать Git

В Gitea найдите Environment ID в каталогах:

```text
gitops/self-service/practicum/requests/
gitops/environments/practicum/self-service/generated/
gitops/self-service/practicum/status/
```

Главная мысль:

> Portal не является вторым control plane. Он создаёт Git artifact, а дальше
> работает та же цепочка controller → Argo CD → DVP → AWX.

## 7. Мои стенды

Откройте вкладку `Мои стенды`:

- видны только environments текущего пользователя;
- кнопка `Обновить` читает актуальный Git status;
- доступны удаление VM и полного стенда;
- для выполняющейся операции показывается текущий этап.

## Ожидаемый результат

Пользователь получает готовый временный стенд без доступа на создание
Kubernetes/DVP-объектов и без ручного обращения к администратору.

