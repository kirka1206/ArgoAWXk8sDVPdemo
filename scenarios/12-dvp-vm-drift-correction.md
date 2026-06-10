# 12. Drift Correction для DVP VM

## Цель

Показать, как Argo CD обнаруживает ручное изменение DVP `VirtualMachine` и
возвращает её спецификацию к состоянию из Git.

Сценарий одновременно объясняет границу ответственности:

- Git и Argo CD управляют декларативной конфигурацией VM;
- DVP выполняет операции жизненного цикла VM;
- AWX настраивает гостевую ОС;
- RBAC ограничивает опасные ручные операции.

## Исходное состояние

- Application `practicum-demo` находится в состоянии `Synced/Healthy`.
- В namespace `practicum-tks` есть активная self-service VM.
- VM и её `VirtualDisk` имеют label `demo.practicum/environment`.
- В Application включено:

```yaml
syncPolicy:
  automated:
    prune: true
    selfHeal: true
```

Выберите environment с VM:

```bash
kubectl get vm -n practicum-tks \
  -l demo.practicum/environment \
  -o custom-columns='VM:.metadata.name,OWNER:.metadata.labels.demo\.practicum/owner,CPU:.spec.cpu.cores,FRACTION:.spec.cpu.coreFraction,MEMORY:.spec.memory.size,PHASE:.status.phase'
```

Для команд ниже задайте имя:

```bash
export VM_NAME=<имя-vm>
export APP_NAME=practicum-demo
export NAMESPACE=practicum-tks
```

## Важное различие: operation и drift

Команды:

```bash
d8 v stop "$VM_NAME" -n "$NAMESPACE"
d8 v start "$VM_NAME" -n "$NAMESPACE"
d8 v restart "$VM_NAME" -n "$NAMESPACE"
```

создают DVP `VirtualMachineOperation`. Они не обязаны изменять `.spec`
`VirtualMachine`, поэтому Argo CD может остаться `Synced`.

При `runPolicy: AlwaysOnUnlessStoppedManually` ручная остановка является
разрешённым состоянием DVP. Для гарантированной демонстрации drift меняйте поле,
которое хранится в Git: CPU или RAM.

## Что меняем в Git

В Git ничего не меняем. Это намеренное ручное изменение live-ресурса в обход
GitOps.

Сначала сохраните ожидаемые значения:

```bash
kubectl get vm "$VM_NAME" -n "$NAMESPACE" \
  -o jsonpath='cores={.spec.cpu.cores} coreFraction={.spec.cpu.coreFraction} memory={.spec.memory.size}{"\n"}'
```

## Пошаговое выполнение

### 1. Открыть интерфейсы

Откройте:

- Argo CD: `http://argocd-practicum.d8case.ru`;
- DKP: проект `practicum-tks` → **Виртуализация** → **Виртуальные машины**.

В Argo CD откройте Application `practicum-demo` и найдите выбранную VM в
дереве ресурсов.

### 2. Запустить наблюдение

В первом терминале:

```bash
kubectl get application "$APP_NAME" -n "$NAMESPACE" -w
```

Во втором терминале:

```bash
kubectl get vm "$VM_NAME" -n "$NAMESPACE" -w
```

### 3. Создать безопасный drift

Измените только RAM:

```bash
kubectl patch vm "$VM_NAME" -n "$NAMESPACE" \
  --type merge \
  -p '{"spec":{"memory":{"size":"640Mi"}}}'
```

Альтернативно можно изменить `coreFraction`:

```bash
kubectl patch vm "$VM_NAME" -n "$NAMESPACE" \
  --type merge \
  -p '{"spec":{"cpu":{"coreFraction":"10%"}}}'
```

Не меняйте оба параметра одновременно: аудитории проще увидеть один diff.

### 4. Показать временное расхождение

```bash
kubectl get vm "$VM_NAME" -n "$NAMESPACE" \
  -o jsonpath='coreFraction={.spec.cpu.coreFraction} memory={.spec.memory.size} needRestart={.status.restartAwaitingChanges}{"\n"}'
```

В Argo CD покажите:

- ресурс VM в состоянии `OutOfSync`;
- diff между live-состоянием и Git;
- автоматическую операцию self-heal.

Состояние `OutOfSync` может быть коротким: self-heal обычно запускается через
несколько секунд.

### 5. Дождаться восстановления

```bash
until [[ "$(kubectl get application "$APP_NAME" -n "$NAMESPACE" \
  -o jsonpath='{.status.sync.status}')" == "Synced" ]]; do
  kubectl get application "$APP_NAME" -n "$NAMESPACE"
  sleep 2
done
```

Проверьте параметры:

```bash
kubectl get vm "$VM_NAME" -n "$NAMESPACE" \
  -o jsonpath='cores={.spec.cpu.cores} coreFraction={.spec.cpu.coreFraction} memory={.spec.memory.size} phase={.status.phase}{"\n"}'
```

Argo CD должен вернуть значения из generated-манифеста Git.

### 6. Проверить необходимость перезапуска

Некоторые изменения ресурсов VM применяются только после controlled restart.
Проверьте:

```bash
kubectl get vm "$VM_NAME" -n "$NAMESPACE" -o yaml |
  sed -n '/restartAwaitingChanges/,+10p'
```

Если DVP показывает ожидающие применения изменения, выполните штатную
операцию:

```bash
d8 v restart "$VM_NAME" -n "$NAMESPACE"
```

Restart является DVP-операцией и сам по себе не должен использоваться как
пример configuration drift.

## Что показывать в Argo CD

1. Application до изменения: `Synced/Healthy`.
2. Diff по `VirtualMachine.spec.memory.size` или
   `VirtualMachine.spec.cpu.coreFraction`.
3. Кратковременный `OutOfSync`.
4. Автоматический self-heal без изменения Git.
5. Возврат в `Synced/Healthy`.

Если `OutOfSync` не успели увидеть в общем списке, откройте историю операций,
events Application и diff конкретного ресурса VM.

## Что показывать в DVP

- имя VM и владельца из labels;
- исходные CPU/RAM;
- изменённое live-значение;
- состояние `Need Restart`, если оно появилось;
- итоговые параметры после self-heal;
- отдельный объект `VirtualMachineOperation` при controlled restart.

## Что показывать в AWX

В основном сценарии AWX не запускается: изменение CPU/RAM относится к
декларативной конфигурации DVP, а не к настройке гостевой ОС.

Это важная граница:

- Argo CD восстанавливает VM-манифест;
- DVP применяет инфраструктурное состояние;
- AWX нужен, когда после создания или изменения VM требуется процедура внутри
  ОС.

Текущий controller не гарантирует повторный запуск уже успешного AWX job после
ручного удаления и пересоздания VM. Для production-процесса нужен отдельный
reconfigure trigger, основанный на новом VM UID, generation или Git revision.

## Проверка через kubectl

```bash
kubectl get application "$APP_NAME" -n "$NAMESPACE"

kubectl get vm "$VM_NAME" -n "$NAMESPACE" \
  -o custom-columns='NAME:.metadata.name,PHASE:.status.phase,CPU:.spec.cpu.cores,FRACTION:.spec.cpu.coreFraction,MEMORY:.spec.memory.size,IP:.status.ipAddress'

kubectl get events -n "$NAMESPACE" \
  --field-selector involvedObject.name="$VM_NAME" \
  --sort-by=.lastTimestamp
```

## Опционально: удаление только VM

Этот блок показывайте только на временном environment, который можно
пересоздать.

Сначала зафиксируйте диск:

```bash
export DISK_NAME="$(kubectl get vm "$VM_NAME" -n "$NAMESPACE" \
  -o jsonpath='{.spec.blockDeviceRefs[0].name}')"

kubectl get vd "$DISK_NAME" -n "$NAMESPACE" -o wide
```

Удалите только `VirtualMachine`:

```bash
kubectl delete vm "$VM_NAME" -n "$NAMESPACE"
```

Не удаляйте `VirtualDisk`.

Ожидаемая цепочка:

```text
VirtualMachine удалена
→ Argo CD обнаруживает отсутствие tracked-ресурса
→ Application становится OutOfSync
→ selfHeal создаёт VirtualMachine заново
→ существующий VirtualDisk подключается повторно
→ DVP запускает VM
→ Application возвращается в Synced/Healthy
```

Проверка:

```bash
kubectl get vm,vd -n "$NAMESPACE" \
  -l demo.practicum/environment
```

Сохранение содержимого ОС зависит от сохранности и повторного подключения того
же `VirtualDisk`.

## Что нельзя делать в демонстрации

Не выполняйте:

```bash
kubectl delete vd "$DISK_NAME" -n "$NAMESPACE"
```

Удаление provisioned `VirtualDisk` может необратимо удалить данные. Argo CD
создаст новый объект диска из golden image, но это будет чистая пересборка, а не
восстановление пользовательских данных.

Также нельзя циклически удалять ресурсы быстрее, чем Argo CD завершает
self-heal: это создаёт гонку контроллеров и делает результат демонстрации
непредсказуемым.

## Ожидаемый результат

- ручное изменение CPU/RAM обнаружено;
- Git не изменялся;
- Argo CD восстановил спецификацию VM;
- Application вернулся в `Synced/Healthy`;
- данные на диске не затронуты;
- при необходимости выполнен controlled restart через DVP operation.

## Rollback

Для изменения CPU/RAM отдельный rollback не нужен: self-heal уже возвращает
desired state из Git.

Если self-heal отключён:

```bash
argocd app sync "$APP_NAME"
```

Если VM была удалена и не пересоздалась:

```bash
kubectl annotate application "$APP_NAME" -n "$NAMESPACE" \
  argocd.argoproj.io/refresh=hard --overwrite

argocd app sync "$APP_NAME"
```

Не создавайте VM вручную другим манифестом: дождитесь применения того же
desired state из Git.

## Рекомендации по RBAC

Для нормальной эксплуатации:

- разрешить Victor start/stop/restart, console, VNC и snapshots;
- запретить удаление GitOps-managed `VirtualDisk`;
- удаление GitOps-managed VM разрешать только в контролируемом break-glass
  процессе;
- отделять ручные VM от GitOps-managed VM namespace или labels;
- запретить Victor менять `VirtualImage`, `ClusterVirtualImage`, Secrets,
  Deployments и RBAC;
- применять admission policy по label
  `demo.practicum/environment`, если одного RBAC недостаточно.

RBAC Kubernetes не умеет ограничивать `delete` по label. Для различения
GitOps-managed и ручных VM надёжнее использовать отдельные namespaces либо
admission policy.

## Пояснение для демонстратора

На этом шаге важно подчеркнуть, что Argo CD контролирует не сам процесс внутри
виртуальной машины, а декларативный объект DVP в Kubernetes API. Victor может
выполнять разрешённые операции жизненного цикла, но ручное изменение CPU или RAM
нарушает desired state из Git. Argo CD обнаруживает это расхождение и возвращает
VM к утверждённой конфигурации.

Self-heal снижает риск случайного drift, но не заменяет RBAC и защиту данных.
Особенно это важно для дисков: VM можно пересоздать, а удалённые данные
автоматически вернуть нельзя.
