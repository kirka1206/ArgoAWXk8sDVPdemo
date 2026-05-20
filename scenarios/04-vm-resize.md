# 04. VM Resize

## Цель

Показать изменение параметров виртуальной машины через Git.

## Исходное состояние

- В Git есть `gitops/environments/prod/values.yaml`.
- В Git есть адаптируемый VM-шаблон `gitops/infrastructure/dvp/postgres-vm.template.yaml`.
- Перед запуском сценария VM manifest должен быть адаптирован под фактический CRD DVP в вашем кластере.

## Что меняем в Git

Файл:

```text
gitops/environments/prod/values.yaml
```

Было:

```yaml
vm:
  cpu: 2
  memory: 4Gi
```

Стало:

```yaml
vm:
  cpu: 4
  memory: 8Gi
```

Если VM-шаблон уже адаптирован под DVP, синхронно измените CPU/RAM в соответствующем VM manifest.

## Пошаговое выполнение

```bash
kubectl get vm postgres-vm -n demo-prod -o yaml
git diff
git add gitops/environments/prod/values.yaml gitops/infrastructure/dvp/postgres-vm.template.yaml
git commit -m "Resize postgres VM"
git push
argocd app get demo-platform
kubectl get vm postgres-vm -n demo-prod
kubectl describe vm postgres-vm -n demo-prod
```

## Что показывать в ArgoCD

- Diff по VM manifest.
- Sync operation.
- Возможное требование controlled restart, если платформа не меняет CPU/RAM live.

## Что показывать в AWX

После изменения VM можно запустить AWX post-config: bootstrap, PostgreSQL tuning и validation. Это показывает, что ArgoCD меняет объект платформы, а AWX выполняет настройку внутри ОС.

## Проверка через kubectl

```bash
kubectl get vm postgres-vm -n demo-prod
kubectl describe vm postgres-vm -n demo-prod
```

## Ожидаемый результат

- VM manifest изменён через Git.
- ArgoCD видит и применяет изменение.
- Параметры VM соответствуют values.yaml или требуют controlled restart, если это ограничение платформы.

## Rollback

```bash
git revert HEAD
git push
argocd app get demo-platform
```

## Пояснение для демонстратора

Не нужно выдумывать VM API на демо. Если точный CRD DVP отличается, честно покажите шаблон и объясните, что в реальном проекте сюда подставляется фактический `VirtualMachine`-ресурс платформы. Главная идея сохраняется: параметры инфраструктуры меняются через Git и проходят тот же audit trail.
