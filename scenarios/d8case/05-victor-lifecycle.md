# 05. Административный lifecycle через портал Victor

## Цель

Показать, как администратор управляет чужими tenant environments без нарушения
GitOps и без прямого `kubectl delete`.

## Исходное состояние

- существует временный environment Alice или Marina;
- Application `practicum-demo` — `Synced/Healthy`;
- Victor входит через группу `practicum-vm-operators`.

## 1. Открыть портал

```text
https://vm-admin-practicum.d8case.ru
```

Пользователь:

```text
victor.melnikov.practicum@demo.local
```

## 2. Показать представления

- `Обзор`: KPI по всем tenant environments;
- `Стенды`: активные стенды;
- `Виртуальные машины`: только environments с VM;
- `Операции`: lifecycle actions;
- `Аудит`: очищенные стенды и последние действия.

Golden builder VM не отображаются, потому что портал читает только status
tenant environments с префиксом `practicum-env-`.

## 3. Выбрать стенд

Используйте поиск по owner:

```text
alice-koroleva-practicum
```

Скопируйте Environment ID:

```bash
export ENV_ID=<environment-id>
export VM_NAME="${ENV_ID}-vm"
```

## 4. Stop/Start/Restart

На стенде с VM:

1. нажмите `Stop`;
2. укажите причину;
3. подтвердите;
4. наблюдайте status и Argo CD;
5. повторите `Start` и `Restart`.

Проверка:

```bash
kubectl get vm "$VM_NAME" -n practicum-tks -w
kubectl get vmop -n practicum-tks \
  -l "demo.practicum/environment=${ENV_ID}"
```

Portal создаёт `EnvironmentAction`. Controller создаёт versioned
`VirtualMachineOperation`. После завершения operation удаляется из desired
state, а action архивируется.

## 5. Удалить только VM

Выберите `Удалить VM`, укажите причину и подтвердите.

Ожидается:

- VM и VirtualDisk удаляются Argo CD prune;
- Deployment, Service и Ingress сохраняются;
- request преобразуется в `app-only`;
- итоговый status — `Ready`, отметка VM removed.

```bash
kubectl get deploy,svc,ingress,vd,vm -n practicum-tks \
  -l "demo.practicum/environment=${ENV_ID}"
```

## 6. Удалить стенд целиком

Выберите `Удалить стенд`, укажите причину и подтвердите.

Статусы:

```text
DeletionRequested → Deleting → Cleaned
```

Controller:

1. отменяет активный AWX job, если он выполняется;
2. архивирует request;
3. удаляет generated desired state;
4. Argo CD prune удаляет ресурсы Environment ID;
5. сохраняет actor, reason, commit и outcome.

## 7. Проверить аудит

```bash
git pull --rebase practicum-gitea main

ls gitops/self-service/practicum/actions-archive |
  grep "$ENV_ID"

jq . "gitops/self-service/practicum/status/${ENV_ID}.json"
```

## Что нельзя делать Victor

Не удаляйте GitOps VM через Web DKP/DVP. Если ресурс остаётся в Git, Argo CD
может восстановить его как drift. Для штатного lifecycle используйте
административный портал.

Не удаляется:

- DKP Project `practicum-tks`;
- namespace `practicum-tks`;
- Gitea, Argo CD, AWX и порталы;
- golden images и builder VM;
- environments других пользователей.

