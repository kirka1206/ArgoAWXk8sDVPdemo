# 06. Drift correction DVP VM

## Цель

Показать, что ручное изменение GitOps-managed VM обнаруживается Argo CD и
возвращается к desired state из Git.

## Важно

Сценарий выполняется только на временной tenant VM. Не используйте golden
builder VM.

## 1. Выбрать VM

```bash
kubectl get vm -n practicum-tks \
  -l demo.practicum/environment \
  -o custom-columns='VM:.metadata.name,ENV:.metadata.labels.demo\.practicum/environment,OWNER:.metadata.labels.demo\.practicum/owner,CPU:.spec.cpu.cores,FRACTION:.spec.cpu.coreFraction,MEMORY:.spec.memory.size,PHASE:.status.phase'
```

```bash
export VM_NAME=<tenant-vm>
export NAMESPACE=practicum-tks
export APP_NAME=practicum-demo
```

Проверьте label:

```bash
kubectl get vm "$VM_NAME" -n "$NAMESPACE" \
  -o jsonpath='{.metadata.labels.demo\.practicum/environment}{"\n"}'
```

## 2. Зафиксировать desired параметры

```bash
kubectl get vm "$VM_NAME" -n "$NAMESPACE" \
  -o jsonpath='cores={.spec.cpu.cores} fraction={.spec.cpu.coreFraction} memory={.spec.memory.size}{"\n"}'
```

Обычно tenant VM имеет:

```text
cores=1 fraction=5% memory=512Mi
```

## 3. Открыть наблюдение

```bash
kubectl get application "$APP_NAME" -n "$NAMESPACE" -w
```

В Argo CD откройте Application `practicum-demo` и выбранную VM.

## 4. Создать drift

Измените только memory:

```bash
kubectl patch vm "$VM_NAME" -n "$NAMESPACE" \
  --type merge \
  -p '{"spec":{"memory":{"size":"640Mi"}}}'
```

## 5. Показать self-heal

```bash
watch -n 1 kubectl get vm "$VM_NAME" -n "$NAMESPACE" \
  -o custom-columns='NAME:.metadata.name,MEMORY:.spec.memory.size,PHASE:.status.phase,RESTART:.status.restartAwaitingChanges'
```

Ожидаемая цепочка:

```text
live memory = 640Mi
→ Application OutOfSync
→ automated selfHeal
→ memory снова 512Mi
→ Application Synced/Healthy
```

OutOfSync может быть очень коротким.

## 6. Controlled restart

Если DVP показывает ожидающие применения изменения, restart выполняйте через
портал Victor, а не прямой DVP-командой. Тогда action и причина сохраняются в
Git-аудите.

## Граница ответственности AWX

В этом сценарии AWX не запускается. CPU/RAM — декларативная инфраструктурная
конфигурация DVP. AWX нужен для изменений внутри гостевой ОС.

## Опционально: ручное удаление VM

Этот блок нужен только для объяснения риска, а не для основного показа:

```bash
kubectl delete vm "$VM_NAME" -n "$NAMESPACE"
```

Argo CD пересоздаст VM, пока она остаётся в Git. Удаление диска может привести
к потере данных. Поэтому штатное удаление выполняется через
`EnvironmentAction` в портале Victor.

