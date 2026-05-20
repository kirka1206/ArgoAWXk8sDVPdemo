const profiles = {
  "app-only": {
    title: "App only",
    description: "Namespace, RBAC, quota, demo app and ingress. No VM.",
    ttlMax: "8h",
    appImages: ["nginx:1.27", "nginx:1.26"],
    vmImages: ["none"],
    resources: ["Namespace", "RBAC", "Quota", "Deployment", "Service", "Ingress"],
    estimate: "pods 8 / cpu 1 / memory 1Gi",
  },
  "app-with-vm": {
    title: "App + VM",
    description: "Demo app plus one minimal DVP VM from an approved golden image.",
    ttlMax: "8h",
    appImages: ["nginx:1.27", "nginx:1.26"],
    vmImages: ["alpine-base-3-23-v1", "alpine-golden-3-23-v1"],
    resources: ["Namespace", "RBAC", "Quota", "Deployment", "Ingress", "DVP VM", "AWX post-config"],
    estimate: "pods 12 / vm 1x5% / memory 2Gi",
  },
  "app-with-postgres-vm": {
    title: "App + PostgreSQL VM",
    description: "Demo app plus minimal DVP VM intended for PostgreSQL post-configuration.",
    ttlMax: "24h",
    appImages: ["nginx:1.27", "nginx:1.26"],
    vmImages: ["alpine-base-3-23-v1", "alpine-golden-3-23-v1"],
    resources: ["Namespace", "RBAC", "Quota", "Deployment", "Ingress", "DVP VM", "PostgreSQL tuning", "AWX validation"],
    estimate: "pods 16 / vm 1x5% / memory 3Gi",
  },
};

let selectedProfile = "app-with-vm";

const el = (id) => document.getElementById(id);

function slug(value) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
}

function renderProfiles() {
  const wrapper = el("profiles");
  wrapper.innerHTML = "";
  Object.entries(profiles).forEach(([key, profile]) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = `profile ${key === selectedProfile ? "active" : ""}`;
    item.innerHTML = `<h3>${profile.title}</h3><p>${profile.description}</p><p>TTL max: ${profile.ttlMax}</p>`;
    item.addEventListener("click", () => {
      selectedProfile = key;
      syncProfileControls();
      renderAll();
    });
    wrapper.appendChild(item);
  });
}

function syncProfileControls() {
  const profile = profiles[selectedProfile];
  el("profileSummary").textContent = selectedProfile;
  el("resourceEstimate").textContent = profile.estimate;

  el("appImage").innerHTML = profile.appImages.map((image) => `<option value="${image}">${image}</option>`).join("");
  el("vmImage").innerHTML = profile.vmImages.map((image) => `<option value="${image}">${image}</option>`).join("");
  el("vmImage").disabled = profile.vmImages[0] === "none";

  if (selectedProfile === "app-only") {
    el("sshToVm").checked = false;
    el("sshToVm").disabled = true;
  } else {
    el("sshToVm").disabled = false;
  }
}

function buildRequest() {
  const envName = slug(el("envName").value || "dev-env");
  const owner = slug(el("owner").value || "developer");
  const team = slug(el("team").value || "platform");
  const profile = profiles[selectedProfile];
  const vmImage = el("vmImage").value;
  const vmBlock =
    selectedProfile === "app-only" ? "" : `  vm:\n    image: ${vmImage}\n    imageKind: ClusterVirtualImage\n`;

  return `apiVersion: demo.platform/v1
kind: EnvironmentRequest
metadata:
  name: ${envName}
spec:
  owner: ${owner}
  team: ${team}
  profile: ${selectedProfile}
  ttl: ${el("ttl").value}
  access:
    exposeIngress: ${el("exposeIngress").checked}
    sshToVm: ${el("sshToVm").checked}
  software:
    appImage: ${el("appImage").value}
${vmBlock}`;
}

function buildCommands() {
  const envName = slug(el("envName").value || "dev-env");
  return `git checkout -b request/${envName}
mkdir -p gitops/self-service/requests
$EDITOR gitops/self-service/requests/${envName}.yaml
git add gitops/self-service/requests/${envName}.yaml
git commit -m "Request self-service environment ${envName}"
git push origin request/${envName}

# For the DKP demo Gitea remote:
git push dkp-gitea request/${envName}

# Then open a pull request to main and wait for Argo CD + AWX status.`;
}

function renderResources() {
  const cards = el("resourceCards");
  cards.innerHTML = "";
  profiles[selectedProfile].resources.forEach((resource) => {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `<strong>${resource}</strong><span>Создаётся после merge request в Git и Argo CD sync.</span>`;
    cards.appendChild(card);
  });
}

function renderAll() {
  renderProfiles();
  renderResources();
  el("yamlOutput").textContent = buildRequest();
  el("commandsOutput").textContent = buildCommands();
}

function copyText(id) {
  navigator.clipboard.writeText(el(id).textContent);
}

["owner", "team", "envName", "ttl", "appImage", "vmImage", "exposeIngress", "sshToVm"].forEach((id) => {
  document.addEventListener("input", (event) => {
    if (event.target && event.target.id === id) renderAll();
  });
  document.addEventListener("change", (event) => {
    if (event.target && event.target.id === id) renderAll();
  });
});

el("copyYaml").addEventListener("click", () => copyText("yamlOutput"));
el("copyCommands").addEventListener("click", () => copyText("commandsOutput"));

syncProfileControls();
renderAll();
