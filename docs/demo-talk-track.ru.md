# Короткий сценарий демонстрации

Этот документ можно использовать как шпаргалку во время живого показа.

## 0. Вступление

Цель стенда: показать, как GitOps и Ansible дополняют друг друга.

Важно сразу зафиксировать границу:

- Argo CD не управляет ОС по SSH.
- Argo CD управляет Kubernetes-ресурсами из Git.
- AWX/Ansible управляет настройкой ОС внутри уже созданных workload'ов.

В демо используются Linux pod'ы, потому что стенд запускается на Docker Desktop. В DVP/KubeVirt на их месте будут VM CRD и гостевые ОС.

## 1. Gitea: исходные артефакты

Открыть `http://localhost:3001`.

Показать репозиторий `codex/demo`.

Что сказать:

> Здесь лежит полный источник истины для демо. Argo CD забирает отсюда Kubernetes manifests, а AWX забирает отсюда Ansible playbook. Это две разные плоскости управления, но один Git-контур.

Показать файлы:

- `gitops/demo-manifests/os-nodes.yaml`
- `awx/os-demo-playbook.yml`

## 2. Argo CD: доставка ресурсов

Открыть `http://localhost:3000`.

Показать application `ansible-os-pods`.

Что сказать:

> Argo CD сравнивает состояние кластера с Git и приводит Kubernetes к описанному состоянию. В этом примере он создает namespace, два Linux pod'а и Services для SSH-доступа.

Команда для терминала:

```bash
kubectl get pods,svc -n demo-os
```

Ожидаемое состояние:

- pod'ы `ol-node-1` и `ol-node-2` в `Running`;
- Services `ol-node-1` и `ol-node-2` открывают порт `22`.

## 3. AWX: настройка ОС

Открыть `http://localhost:3002`.

Показать job template `Configure OS pods`.

Что сказать:

> AWX работает уже не с Kubernetes-манифестами, а с ОС внутри workload'ов. Он подключается по SSH, собирает facts, записывает файл и устанавливает пакет.

Запустить:

```bash
./scripts/run-demo-job.sh
```

Показать в output:

- `changed` на обоих host'ах;
- `failed=0`;
- содержимое marker-файла.

## 4. Проверка результата

Команды:

```bash
kubectl exec -n demo-os deploy/ol-node-1 -- cat /etc/ansible-managed-by-awx
kubectl exec -n demo-os deploy/ol-node-2 -- cat /etc/ansible-managed-by-awx
```

Что сказать:

> Этот файл появился не из Kubernetes manifest. Его создал AWX через Ansible внутри ОС. Но сами pod'ы, в которых он появился, были доставлены через Argo CD из Git.

## 5. Мостик к DVP/KubeVirt

Что сказать:

> В DVP/KubeVirt вместо этих demo pod'ов будут `VirtualMachine`, `VirtualDisk`, `VirtualImage`, `VirtualMachineClass` и связанные Services. Argo CD будет синхронизировать эти CRD, а AWX будет настраивать гостевую ОС внутри VM.

## 6. Вывод

Финальная формулировка:

> Argo CD отвечает за декларативное состояние платформы. AWX отвечает за операционную настройку ОС. Вместе они дают воспроизводимый путь от Git до работающего и настроенного workload'а.

