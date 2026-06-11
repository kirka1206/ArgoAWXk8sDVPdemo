# 03. Self-service через Git и YAML

## Цель

Показать, что разработчик коммитит только декларативную заявку, а controller,
Argo CD, DVP и AWX создают стенд без ручного `kubectl apply`.

Все ресурсы создаются в namespace `practicum-tks`. Новый DKP Project или
namespace для каждой заявки не создаётся.

## 1. Подготовить переменные

```bash
cd /Users/kir/code/ArgoAWXk8sDVPdemo
git fetch practicum-gitea main
git pull --rebase practicum-gitea main

export ENV_ID="practicum-env-marina-demo-$(date +%H%M%S)"
export CREATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "$ENV_ID $CREATED_AT"
```

Имя должно:

- начинаться с `practicum-env-`;
- содержать только lowercase, цифры и `-`;
- быть не длиннее 63 символов.

## 2. Создать EnvironmentRequest

```bash
cat > "gitops/self-service/practicum/requests/${ENV_ID}.yaml" <<EOF
{
  "apiVersion": "demo.practicum/v1",
  "kind": "EnvironmentRequest",
  "metadata": {
    "name": "${ENV_ID}"
  },
  "spec": {
    "owner": "marina-volkova-practicum",
    "email": "marina.volkova.practicum@demo.local",
    "groups": ["practicum-qa-devs"],
    "profile": "app-with-vm",
    "purpose": "demo",
    "ttl": "2h",
    "createdAt": "${CREATED_AT}"
  }
}
EOF
```

Разрешённые профили:

| Profile | Результат |
|---|---|
| `app-only` | Deployment, Service, Ingress |
| `app-with-vm` | приложение и минимальная Linux VM |
| `app-with-postgres-vm` | приложение, VM и PostgreSQL post-config |

Для PostgreSQL добавьте:

```json
"postgresql": {"version": "18"}
```

Поддерживаются версии `16`, `17`, `18`.

## 3. Commit и push

```bash
git add "gitops/self-service/practicum/requests/${ENV_ID}.yaml"
git commit -m "Request practicum environment ${ENV_ID}"
git push practicum-gitea main
```

GitHub является копией проекта, но live Argo CD читает Gitea.

## 4. Наблюдать Git

В Gitea покажите появление:

```text
gitops/self-service/practicum/requests/<environment-id>.yaml
gitops/environments/practicum/self-service/generated/<environment-id>/
gitops/self-service/practicum/status/<environment-id>.json
```

Controller может создать несколько status-коммитов. Это штатно.

## 5. Наблюдать Argo CD

```bash
watch -n 2 kubectl get application practicum-demo -n practicum-tks
```

В UI Argo CD найдите ресурсы по Environment ID.

## 6. Наблюдать Kubernetes/DVP

```bash
kubectl get deploy,svc,ingress,vd,vm -n practicum-tks \
  -l "demo.practicum/environment=${ENV_ID}" -w
```

Для VM:

```bash
kubectl get vm "${ENV_ID}-vm" -n practicum-tks -o wide
```

## 7. Наблюдать AWX

В AWX откройте Job Template:

```text
Practicum Environment Post-Config
```

Controller запустит job после готовности VM и guest agent.

## 8. Прочитать итоговый status

```bash
git pull --rebase practicum-gitea main
jq . "gitops/self-service/practicum/status/${ENV_ID}.json"
```

Ожидается:

- `state: Ready`;
- приложение `ready 1/1`;
- VM `Running`;
- IP VM;
- AWX `successful`;
- команда `d8 v ssh`.

## 9. Доступ

```bash
kubectl get ingress "$ENV_ID" -n practicum-tks

d8 v ssh "ansible@${ENV_ID}-vm" \
  --namespace practicum-tks \
  --identity-file local/practicum-ssh/id_ed25519 \
  --local-ssh
```

## Cleanup

Удаляйте стенд через портал пользователя или Victor. Не удаляйте request и
generated-каталог вручную во время демонстрации: lifecycle должен остаться
аудитируемым.

