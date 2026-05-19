# Use cases и сценарии применения

## 1. GitOps-доставка вычислительных ресурсов

Инженер меняет манифесты в Git. Argo CD обнаруживает изменение и приводит Kubernetes-кластер к описанному состоянию.

В локальном демо это два Linux pod'а:

- `ol-node-1`
- `ol-node-2`

В DVP/KubeVirt ту же роль могут выполнять:

- `VirtualMachine`
- `VirtualDisk`
- `VirtualImage`
- `VirtualMachineClass`

Ценность: состояние инфраструктуры версионируется, проходит review и может быть восстановлено из Git.

## 2. Настройка ОС после создания ресурса

После того как Argo CD создал workload'ы, AWX запускает Ansible playbook и подключается к ним по SSH. Playbook записывает marker-файл и устанавливает пакет.

Ценность: lifecycle Kubernetes-объектов и lifecycle ОС разделены, но связаны в единую операционную модель.

## 3. Единый audit trail

Gitea хранит:

- Kubernetes-манифесты;
- Ansible playbook;
- inventory reference.

Argo CD показывает sync status и расхождения с Git. AWX показывает историю job'ов, stdout, recap и результат по каждому host'у.

Ценность: можно объяснить, что изменилось, каким инструментом и на каком уровне.

## 4. Подготовка к DVP/KubeVirt внедрению

Демо можно использовать до развертывания полноценной виртуализационной платформы. На ноутбуке показывается операционная модель, а в целевой среде pod'ы заменяются на VM CRD.

Ценность: команда и заказчик обсуждают не абстрактный GitOps, а конкретный рабочий процесс.

## 5. Разделение зон ответственности

Argo CD отвечает за декларативное состояние платформы:

- какие workload'ы существуют;
- какие Services созданы;
- какие labels/selectors используются;
- какие классы, диски или образы подключены в DVP/KubeVirt-варианте.

AWX отвечает за действия внутри ОС:

- установка пакетов;
- настройка файлов;
- запуск команд;
- сбор facts;
- проверка состояния.

Ценность: снижается путаница между platform management и configuration management.

## Демонстрационный сценарий

### Подготовка

1. Запустить чистый Docker Desktop Kubernetes.
2. Выполнить:

   ```bash
   ./scripts/bootstrap.sh
   ```

3. Открыть интерфейсы:

   - Gitea: `http://localhost:3001`
   - Argo CD: `http://localhost:3000`
   - AWX: `http://localhost:3002`

### Шаг 1. Показать Git как источник истины

Открыть Gitea и репозиторий `codex/demo`.

Показать файлы:

- `gitops/demo-manifests/os-nodes.yaml`
- `awx/os-demo-playbook.yml`

Сообщение для аудитории: в одном Git-репозитории лежит и декларативное состояние платформы, и автоматизация настройки ОС.

### Шаг 2. Показать работу Argo CD

Открыть Argo CD Application `ansible-os-pods`.

Показать:

- `Synced`
- `Healthy`
- дерево ресурсов приложения.

Проверить из терминала:

```bash
kubectl get pods,svc -n demo-os
```

Сообщение для аудитории: Argo CD создал Linux pod'ы и Services из Git и продолжает контролировать их desired state.

### Шаг 3. Показать работу AWX

Открыть AWX job template `Configure OS pods`.

Запустить job из UI или командой:

```bash
./scripts/run-demo-job.sh
```

Показать в output:

- `Gathering Facts`;
- запись `/etc/ansible-managed-by-awx`;
- установку `htop`;
- recap с `failed=0`.

Сообщение для аудитории: AWX не создает Kubernetes-ресурсы. Он выполняет настройку внутри ОС workload'ов, которые доставил Argo CD.

### Шаг 4. Проверить результат внутри workload'ов

```bash
kubectl exec -n demo-os deploy/ol-node-1 -- cat /etc/ansible-managed-by-awx
kubectl exec -n demo-os deploy/ol-node-2 -- cat /etc/ansible-managed-by-awx
```

Ожидаемый результат:

```text
managed_by=AWX
deployed_by=Argo CD
host=...
kernel=...
```

### Шаг 5. Объяснить перенос на DVP/KubeVirt

| Локальное демо | DVP/KubeVirt |
| --- | --- |
| Linux pod Deployment | `VirtualMachine` |
| Container image/bootstrap | `VirtualImage`, cloud-init или Sysprep |
| Kubernetes Service для SSH | Service или platform-specific publishing |
| AWX SSH target | DNS/IP гостевой ОС |

Финальная мысль: Argo CD управляет заявленным состоянием Kubernetes/DVP-платформы, AWX управляет конфигурацией гостевой ОС.

