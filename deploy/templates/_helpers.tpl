{{/*
Naming + label helpers for the atlas-mcp-doc-search chart (atlas-docs/04 §4.2).
*/}}

{{- define "atlas-mcp-doc-search.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "atlas-mcp-doc-search.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "atlas-mcp-doc-search.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Labels common to every rendered object. */}}
{{- define "atlas-mcp-doc-search.labels" -}}
helm.sh/chart: {{ include "atlas-mcp-doc-search.chart" . }}
{{ include "atlas-mcp-doc-search.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: atlas
{{- end -}}

{{/* Stable selector labels — must not change across releases. */}}
{{- define "atlas-mcp-doc-search.selectorLabels" -}}
app.kubernetes.io/name: {{ include "atlas-mcp-doc-search.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/* ServiceAccount name (created or referenced). */}}
{{- define "atlas-mcp-doc-search.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "atlas-mcp-doc-search.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/* The image reference; tag defaults to the chart appVersion when unset. */}}
{{- define "atlas-mcp-doc-search.image" -}}
{{- $tag := .Values.image.tag | default .Chart.AppVersion -}}
{{- printf "%s:%s" .Values.image.repository $tag -}}
{{- end -}}

{{/*
Pod template spec shared by the Deployment and the Rollout.
*/}}
{{- define "atlas-mcp-doc-search.podSpec" -}}
metadata:
  labels:
    {{- include "atlas-mcp-doc-search.selectorLabels" . | nindent 4 }}
    {{- with .Values.podLabels }}
    {{- toYaml . | nindent 4 }}
    {{- end }}
  {{- with .Values.podAnnotations }}
  annotations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
spec:
  serviceAccountName: {{ include "atlas-mcp-doc-search.serviceAccountName" . }}
  {{- with .Values.imagePullSecrets }}
  imagePullSecrets:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  securityContext:
    {{- toYaml .Values.podSecurityContext | nindent 4 }}
  containers:
    - name: {{ .Chart.Name }}
      image: {{ include "atlas-mcp-doc-search.image" . }}
      imagePullPolicy: {{ .Values.image.pullPolicy }}
      securityContext:
        {{- toYaml .Values.securityContext | nindent 8 }}
      ports:
        - name: http
          containerPort: {{ .Values.containerPort }}
          protocol: TCP
      env:
        {{- with .Values.env }}
        {{- toYaml . | nindent 8 }}
        {{- end }}
      startupProbe:
        httpGet:
          path: {{ .Values.probes.path }}
          port: http
        failureThreshold: {{ .Values.probes.startup.failureThreshold }}
        periodSeconds: {{ .Values.probes.startup.periodSeconds }}
      livenessProbe:
        httpGet:
          path: {{ .Values.probes.path }}
          port: http
        initialDelaySeconds: {{ .Values.probes.liveness.initialDelaySeconds }}
        periodSeconds: {{ .Values.probes.liveness.periodSeconds }}
        timeoutSeconds: {{ .Values.probes.liveness.timeoutSeconds }}
        failureThreshold: {{ .Values.probes.liveness.failureThreshold }}
      readinessProbe:
        httpGet:
          path: {{ .Values.probes.path }}
          port: http
        initialDelaySeconds: {{ .Values.probes.readiness.initialDelaySeconds }}
        periodSeconds: {{ .Values.probes.readiness.periodSeconds }}
        timeoutSeconds: {{ .Values.probes.readiness.timeoutSeconds }}
        failureThreshold: {{ .Values.probes.readiness.failureThreshold }}
      resources:
        {{- toYaml .Values.resources | nindent 8 }}
      {{- if .Values.secrets.enabled }}
      volumeMounts:
        - name: secrets-store
          mountPath: {{ .Values.secrets.mountPath }}
          readOnly: true
      {{- end }}
  {{- if .Values.secrets.enabled }}
  volumes:
    - name: secrets-store
      csi:
        driver: secrets-store.csi.k8s.io
        readOnly: true
        volumeAttributes:
          secretProviderClass: {{ include "atlas-mcp-doc-search.fullname" . }}
  {{- end }}
  {{- with .Values.nodeSelector }}
  nodeSelector:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  {{- with .Values.affinity }}
  affinity:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  {{- with .Values.tolerations }}
  tolerations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
{{- end -}}
