# 04. VM Resize

## Цель

Показать изменение параметров виртуальной машины через Git.

## Исходное состояние

- В Git есть `gitops/environments/prod/values.yaml`.
- В Git есть реальный минимальный DVP manifest `gitops/environments/prod/dvp-postgres-vm.yaml`.
- VM уже развернута с минимальными ресурсами для стенда: `1` core, `coreFraction: 5%`, `512Mi` RAM, disk `256Mi`.

## Что меняем в Git

Файл:

```text
gitops/environments/prod/values.yaml
```

Было:

```yaml
vm:
  cpu: 1
  coreFraction: 5%
  memory: 512Mi
```

Стало:

```yaml
vm:
  cpu: 1
  coreFraction: 10%
  memory: 1Gi
```

Для бережного стенда не увеличивайте количество core без необходимости. Для демонстрации resize достаточно поднять `coreFraction` с `5%` до `10%` или RAM с `512Mi` до `1Gi`.

## Пошаговое выполнение

```bash
kubectl get vm postgres-vm -n demo-prod -o yaml
git diff
git add gitops/environments/prod/values.yaml gitops/environments/prod/dvp-postgres-vm.yaml
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

На этом шаге важно не раздувать стенд. Для демонстрации достаточно минимальной VM и небольшого изменения `coreFraction` или RAM. Главная идея сохраняется: параметры инфраструктуры меняются через Git и проходят тот же audit trail.
