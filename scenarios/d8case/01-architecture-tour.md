# 01. Архитектура GitOps + DVP + AWX

## Цель

До изменения ресурсов объяснить аудитории весь pipeline и показать, где
настроена каждая связь.

## Крупноблочная схема

```plantuml
@startuml
title GitOps-стенд: основные компоненты и связи
left to right direction
skinparam shadowing false
skinparam roundcorner 8

actor "Администратор\nплатформы" as Admin
actor "Разработчик" as Dev

rectangle "Git-репозиторий\nGitea" as Git #EAF2FF {
  file "Manifests Kubernetes и DVP\nобразы, VM, диски,\nactiveGoldenImage" as Manifests
  file "Ansible playbook" as Playbooks
  file "Заявки и статусы\nпользовательских стендов" as Requests
}

rectangle "Argo CD" as Argo #DDF4E5 {
  component "Application\npracticum-demo" as App
}

rectangle "Kubernetes\nnamespace practicum-tks" as K8s #FFF5D9 {
  component "Python-сервис\nобработки заявок\npracticum-request-controller" as Controller
  component "AWX" as AWX
  component "DVP" as DVP
  database "Хранилище DVP" as Storage
}

rectangle "Временная VM\nдля сборки образа" as Builder #F3E8FF
rectangle "Пользовательская\nвиртуальная машина" as TenantVM #F3E8FF

Admin --> Git : создаёт и изменяет\nконфигурацию
Dev --> Git : создаёт заявку\nчерез портал или Git

Git --> App : repository webhook\nи чтение Git
App --> Manifests : читает желаемое\nсостояние
Argo --> K8s : применяет manifests\nи поддерживает состояние

Controller --> Requests : читает заявки\nи статусы
Controller --> Git : создаёт manifests\nи записывает статусы
Controller --> AWX : запускает задачи\nнастройки и проверки

DVP --> Storage : создаёт и хранит\nобразы и диски
DVP --> Builder : создаёт временную VM\nдля подготовки образа
AWX --> Builder : настраивает и проверяет\nгостевую ОС
Builder --> DVP : подготовленный диск\nстановится новой версией образа

DVP --> TenantVM : создаёт новую VM\nиз активного образа
AWX --> TenantVM : выполняет настройку\nи проверку ОС

note bottom of Argo
Argo CD Application задаёт:
репозиторий, ветку, путь к manifests
и целевой namespace.
end note

note bottom of Controller
Это наша Python-программа.
Она не применяет ресурсы напрямую:
она меняет Git, а Argo CD
применяет изменения в кластере.
end note

@enduml
```

## Поток заявки

```mermaid
flowchart LR
  User["Разработчик или Victor"] --> Portal["Web portal или Git commit"]
  Portal --> Gitea["Gitea practicum/practicum-demo"]
  Gitea --> Controller["practicum-request-controller"]
  Gitea --> Argo["Argo CD practicum-demo"]
  Controller --> Gitea
  Argo --> K8s["Kubernetes и DVP"]
  Controller --> AWX["AWX Job Template"]
  AWX --> VM["Гостевая ОС VM"]
  K8s --> Controller
  AWX --> Controller
  Controller --> Status["Status в Git"]
  Status --> Portal
```

## 1. Показать Git

Откройте:

```text
http://gitea-practicum.d8case.ru/practicum/practicum-demo
```

Покажите:

```text
gitops/environments/practicum/
gitops/self-service/practicum/requests/
gitops/self-service/practicum/status/
gitops/self-service/practicum/actions/
```

Объяснение:

- `requests` — намерение пользователя;
- `generated` — desired state Kubernetes/DVP;
- `actions` — lifecycle-команды;
- `status` — результат controller, DVP, Argo CD и AWX.

## 2. Показать настройку Argo CD

Откройте:

```text
http://argocd-practicum.d8case.ru
```

Application:

```text
practicum-demo
```

CLI-проверка:

```bash
kubectl get application practicum-demo -n practicum-tks -o yaml |
  sed -n '/source:/,/syncPolicy:/p'
```

Покажите:

- repository URL Gitea;
- target revision `main`;
- path `gitops/environments/practicum`;
- automated sync, prune и self-heal.

Argo CD строит дерево не из README. Оно формируется из owner references,
labels, namespace и фактически применённых Kubernetes-ресурсов.

## 3. Показать controller

```bash
kubectl get deploy practicum-request-controller -n practicum-tks
kubectl logs deploy/practicum-request-controller -n practicum-tks --tail=50
```

Controller:

1. читает `EnvironmentRequest`;
2. проверяет owner, group, profile, TTL и лимиты;
3. создаёт generated manifests через атомарный commit;
4. ждёт готовности приложения и VM;
5. запускает AWX;
6. записывает status обратно в Git.

Это не controller Argo CD. Это отдельный компонент данного demo-проекта.

## 4. Показать AWX

Откройте:

```text
http://awx-practicum.d8case.ru
```

Покажите:

- Project с репозиторием `practicum-demo`;
- Job Template `Practicum Environment Post-Config`;
- Workflow/Jobs golden image;
- inventory host, создаваемый или обновляемый для VM.

Argo CD не выполняет Ansible. AWX запускает playbook, а controller вызывает AWX
API и затем читает статус job.

## 5. Показать DVP

В Web DKP откройте Project `practicum-tks`, затем виртуальные машины и образы.

```bash
kubectl get vi,vd,vm,vmop -n practicum-tks -o wide
```

## Ожидаемый вывод рассказа

> Git хранит намерение и desired state. Controller реализует бизнес-процесс.
> Argo CD синхронизирует Kubernetes/DVP-объекты. DVP исполняет виртуализацию.
> AWX меняет состояние внутри гостевой ОС. Portal только создаёт запрос и
> показывает status, но не удаляет ресурсы напрямую.
