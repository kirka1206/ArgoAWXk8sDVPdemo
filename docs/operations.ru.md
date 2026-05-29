# Операционная памятка

## Контуры стенда

В проекте есть два рабочих контура:

- `ansible-os-pods`: локальный pod-only сценарий для Docker Desktop и базовой демонстрации Argo CD + AWX.
- `demo-platform`: расширенный DKP/DVP сценарий с `demo-app`, tenant `customer-a` и минимальной DVP VM `postgres-vm`.

Для переноса на другой DKP/DVP стенд используйте:

- [Пререквизиты стенда](prerequisites.ru.md);
- [Детальный план переноса](migration-plan.ru.md).

## Запуск локального стенда

```bash
./scripts/bootstrap.sh
```

Скрипт устанавливает:

- Gitea;
- Argo CD;
- AWX;
- demo Linux pod'ы;
- AWX inventory, project, credentials, execution environment и job template.

## Запуск DKP/DVP профиля

```bash
./scripts/deploy-dkp.sh
```

Проверить kube-context:

```bash
kubectl config current-context
```

Ожидаемый context:

```text
codex-api.d8.kir.lab
```

Для нового стенда передайте параметры:

```bash
CONTEXT=<target-context> \
GITEA_HOST=gitea-awx.<target-domain> \
ARGOCD_HOST=argocd-awx.<target-domain> \
AWX_HOST=awx-demo.<target-domain> \
./scripts/deploy-dkp.sh
```

Проверить Ingress:

```bash
kubectl get ingress -A | grep -E 'gitea-awx|argocd-awx|awx-demo'
```

## Повторно открыть локальные интерфейсы

```bash
./scripts/port-forward.sh
```

Локальные URL:

- Gitea: `http://localhost:3001`
- Argo CD: `http://localhost:3000`
- AWX: `http://localhost:3002`

DKP URL:

- Gitea: `http://gitea-awx.d8.kir.lab`
- Argo CD: `http://argocd-awx.d8.kir.lab`
- AWX: `http://awx-demo.d8.kir.lab`

## Запуск AWX job

Локально:

```bash
./scripts/run-demo-job.sh
```

В DKP:

```bash
AWX_URL=http://awx-demo.d8.kir.lab ./scripts/run-demo-job.sh
```

Скрипт:

1. находит AWX job template `Configure OS pods`;
2. запускает job;
3. ждёт финальный статус;
4. выводит stdout;
5. проверяет marker-файлы в pod'ах `demo-os`.

## Проверка Argo CD

```bash
kubectl get application -n argocd
kubectl get application -n argocd ansible-os-pods
kubectl get application -n argocd demo-platform
```

Ожидаемо:

```text
ansible-os-pods   Synced   Healthy
demo-platform     Synced   Healthy
```

## Проверка pod-only сценария

```bash
kubectl get pods,svc -n demo-os
kubectl exec -n demo-os deploy/ol-node-1 -- cat /etc/ansible-managed-by-awx
kubectl exec -n demo-os deploy/ol-node-2 -- cat /etc/ansible-managed-by-awx
```

## Проверка DVP-сценария

```bash
kubectl get deploy,svc,ingress -n demo-prod
kubectl get vi,vd,vm -n demo-prod -o wide
kubectl describe vm postgres-vm -n demo-prod
```

Ожидаемые параметры VM:

```text
postgres-vm Running
1 core
coreFraction 5%
memory 512Mi
disk 256Mi
```

## Проверка tenant

```bash
kubectl get ns customer-a
kubectl get resourcequota -n customer-a
kubectl get limitrange -n customer-a
kubectl get rolebinding -n customer-a
kubectl get deploy,svc,ingress -n customer-a
```

## Частые проблемы

### 401 при запуске AWX job

Скорее всего, скрипт попал в старый AWX через `localhost:3002`.

Проверить:

```bash
curl -fsS http://localhost:3002/api/v2/ping/
curl -fsS http://awx-demo.d8.kir.lab/api/v2/ping/
```

Для DKP используйте:

```bash
AWX_URL=http://awx-demo.d8.kir.lab ./scripts/run-demo-job.sh
```

### DVP VM зависла в Pending

Проверить image, disk, VM и events:

```bash
kubectl get vi,vd,vm -n demo-prod -o wide
kubectl describe vi demo-alpine-cloud -n demo-prod
kubectl describe vd postgres-vm-root -n demo-prod
kubectl describe vm postgres-vm -n demo-prod
kubectl get events -n demo-prod --sort-by=.lastTimestamp
```

На первом запуске DVP скачивает image и импортирует disk. Это может занять несколько минут.

### AWX долго стартует

```bash
kubectl get job,pods -n awx
kubectl logs -n awx job/awx-demo-migration-24.6.1 --tail=100
```

### Argo CD Application не Synced

```bash
kubectl describe application -n argocd demo-platform
kubectl describe application -n argocd ansible-os-pods
```

Типовые причины:

- Gitea repo не обновлён;
- указан неверный path;
- CRD DVP ещё не готов;
- namespace или StorageClass недоступны.
- `gitops/self-service/generated/kustomization.yaml` содержит невалидную комбинацию `resources: []` и вложенных `- <name>`.

Валидный пустой вариант:

```yaml
resources: []
```

Валидный вариант со стендами:

```yaml
resources:
  - dev-example
```

## Master node scheduling

В стендовом кластере taint с master node снят, чтобы scheduler мог использовать ресурсы `dmaster`.

Проверка:

```bash
kubectl get nodes -o json | jq -r '.items[] | .metadata.name as $n | "\($n)\t\(.spec.taints // [])"'
kubectl get pods -A -o wide | grep dmaster
```

## Rollback

Для сценарных изменений:

```bash
git revert HEAD
git push
argocd app get demo-platform
```

## Очистка

Локальный cleanup:

```bash
./scripts/destroy.sh
```

Перед удалением DVP-ресурсов проверьте, что они не нужны:

```bash
kubectl get vi,vd,vm -n demo-prod
```
