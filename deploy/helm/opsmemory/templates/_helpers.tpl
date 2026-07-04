{{- define "opsmemory.name" -}}
{{ .Chart.Name }}
{{- end }}

{{- define "opsmemory.fullname" -}}
{{ .Release.Name }}-{{ .Chart.Name }}
{{- end }}

{{- define "opsmemory.labels" -}}
app.kubernetes.io/name: {{ include "opsmemory.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "opsmemory.selectorLabels" -}}
app.kubernetes.io/name: {{ include "opsmemory.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
