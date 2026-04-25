{{/*
Expand the name of the chart.
*/}}
{{- define "odoo.name" -}}
{{- default "odoo" .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "odoo.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default "odoo" .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "odoo.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "odoo.labels" -}}
helm.sh/chart: {{ include "odoo.chart" . }}
{{ include "odoo.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "odoo.selectorLabels" -}}
app.kubernetes.io/name: {{ include "odoo.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "odoo.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "odoo.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Resolve the TLS Secret name produced by cert-manager. Defaults to
`<fullname>-tls` so multiple chart instances in the same namespace
do not collide on a hardcoded secret name. Overridable via
`certmanager.secretName`.
*/}}
{{- define "odoo.tlsSecretName" -}}
{{- default (printf "%s-tls" (include "odoo.fullname" .)) .Values.certmanager.secretName -}}
{{- end -}}

{{/*
Resolve the TLS Secret name an Ingress should reference. Cascade:
  1. Explicit `ingress.tlsSecretName` (user override)
  2. cert-manager managed secret if cert-manager is enabled
  3. Empty (Ingress is rendered without TLS section)
*/}}
{{- define "odoo.ingress.tlsSecretName" -}}
{{- if .Values.ingress.tlsSecretName -}}
{{- .Values.ingress.tlsSecretName -}}
{{- else if .Values.certmanager.enabled -}}
{{- include "odoo.tlsSecretName" . -}}
{{- end -}}
{{- end -}}

{{/*
Resolve the TLS Secret name a Traefik IngressRoute should reference.
Same cascade as `odoo.ingress.tlsSecretName`.
*/}}
{{- define "odoo.ingressroute.tlsSecretName" -}}
{{- if .Values.ingressroute.tlsSecretName -}}
{{- .Values.ingressroute.tlsSecretName -}}
{{- else if .Values.certmanager.enabled -}}
{{- include "odoo.tlsSecretName" . -}}
{{- end -}}
{{- end -}}

{{/*
Create additional odoo config
*/}}
{{- define "odoo.addConfig" -}}
{{- if .Values.additionalConfig }}
{{ .Values.additionalConfig }}
{{- end }}
{{- range $key, $value := .Values }}
{{- if and (hasPrefix "add_config_" $key) $value }}
{{ $key | trimPrefix "add_config_" }} = {{ $value }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create odoo cron config
*/}}
{{- define "odoo-cron.config" -}}
[options]
admin_passwd = {{ .Values.adminPassword }}
{{- if not .Values.databaseManager }}
list_db = False
{{- end }}
proxy_mode = True
log_handler = [':INFO']
log_level = info
data_dir = /data
workers = 0
max_cron_threads = {{ .Values.cronThreads }}
{{- if .Values.queue }}
server_wide_modules = web,queue_job
{{- end }}
limit_time_real_cron = 0
limit_time_real = 0
limit_memory_soft = 0
limit_memory_hard = 0
{{ include "odoo.addConfig" . }}
{{- if .Values.additionalCronConfig }}
{{ .Values.additionalCronConfig }}
{{- end }}
{{- end }}

{{/*
Create odoo worker config
*/}}
{{- define "odoo.config" -}}
[options]
admin_passwd = {{ .Values.adminPassword }}
{{- if not .Values.databaseManager }}
list_db = False
{{- end }}
proxy_mode = True
log_handler = [':INFO']
log_level = info
data_dir = /data
workers = {{ .Values.workers }}
{{- if gt (int .Values.workers) 0 }}
max_cron_threads = {{ .Values.cronWorkers }}
limit_time_real_cron = 0
{{- else }}
max_cron_threads = {{ .Values.cronThreads }}
limit_time_real_cron = 0
limit_time_real = 0
limit_memory_soft = 0
limit_memory_hard = 0
{{- if .Values.queue }}
server_wide_modules = web,queue_job
{{- end }}
{{- end }}
{{ include "odoo.addConfig" . }}
{{- end }}