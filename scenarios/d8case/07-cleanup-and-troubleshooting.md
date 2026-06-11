# 07. Cleanup и troubleshooting

## Штатный cleanup

### Пользователь

```text
selfservice-practicum.d8case.ru
→ Мои стенды
→ Удалить стенд
```

Пользователь может удалить только свой environment.

### Victor

```text
vm-admin-practicum.d8case.ru
→ Стенды
→ выбрать Environment ID
→ Удалить стенд
→ указать причину
```

## Проверка cleanup

```bash
export ENV_ID=<environment-id>

kubectl get deploy,svc,ingress,vd,vm,vmop -n practicum-tks \
  -l "demo.practicum/environment=${ENV_ID}"

git pull --rebase practicum-gitea main
jq . "gitops/self-service/practicum/status/${ENV_ID}.json"
```

Ожидается:

- Kubernetes/DVP-ресурсов Environment ID нет;
- status `Cleaned`;
- request находится в `archive`;
- action находится в `actions-archive`;
- Application `Synced/Healthy`.

## Не удалять

```text
namespace/practicum-tks
VirtualImage/practicum-alpine-golden-3-23-v1
VirtualImage/practicum-alpine-golden-3-23-v2
VirtualMachine/practicum-golden-builder-vm
VirtualMachine/practicum-golden-builder-v2-vm
```

## Диагностика Argo CD

```bash
kubectl get application practicum-demo -n practicum-tks
kubectl describe application practicum-demo -n practicum-tks
kubectl logs deploy/argocd-application-controller -n practicum-tks --tail=100
kubectl logs deploy/argocd-repo-server -n practicum-tks --tail=100
```

Если provisioned VirtualDisk отклоняет изменение data source, не patch'ите
его. Создайте новый versioned disk/image.

## Диагностика controller

```bash
kubectl get deploy practicum-request-controller -n practicum-tks
kubectl logs deploy/practicum-request-controller -n practicum-tks --tail=200
```

`capacity-limit` означает достижение:

```text
MAX_ACTIVE_ENVIRONMENTS=7
MAX_ACTIVE_VMS=7
```

Лимиты задаются env-переменными Deployment controller.

## Диагностика AWX

```bash
kubectl get pods -n practicum-tks | grep practicum-awx
kubectl logs deploy/practicum-awx-task -n practicum-tks --tail=100
```

В UI AWX откройте Job ID из status environment.

## Диагностика порталов

```bash
kubectl get deploy,svc,ingress,dexauthenticator,certificate \
  -n practicum-tks | grep -E 'selfservice|vm-admin'

kubectl logs deploy/practicum-self-service-portal \
  -n practicum-tks --tail=100

kubectl logs deploy/practicum-vm-admin-portal \
  -n practicum-tks --tail=100
```

При `IngressResponses5xx` проверьте backend logs и `/api/environments`.
Административный portal использует cache и один архивный запрос к Gitea.

## Финальная проверка стенда

```bash
kubectl get application practicum-demo -n practicum-tks
kubectl get vi,vd,vm -n practicum-tks -o wide
kubectl get deploy -n practicum-tks
git status
```

