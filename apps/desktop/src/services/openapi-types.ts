/* Generated from contracts/openapi/sysmind-local-api.json by scripts/generate-ts-types.py.
 * Do not edit by hand. Run: python scripts/generate-ts-types.py
 */

export type components = {
  schemas: {
    ActionListResponse: {
      items: Array<components['schemas']['ActionResponse']>;
    }
    ActionResponse: {
      id: string;
      plan_id: string;
      diagnosis_id: string;
      tool_name: string;
      tool_version: string;
      target_name: string;
      source_kind: string;
      status: string;
      recovery_available: boolean;
      error_code: string;
      error_message: string;
      created_at: string;
      updated_at: string;
    }
    AgentBudgetDto: {
      max_rounds: number;
      max_tool_calls: number;
      timeout_seconds: number;
      max_parallel_tools: number;
    }
    AgentBudgetRequest: {
      max_rounds?: number;
      max_tool_calls?: number;
      timeout_seconds?: number;
      max_parallel_tools?: number;
    }
    AgentTaskListResponse: {
      items: Array<components['schemas']['AgentTaskResponse']>;
    }
    AgentTaskResponse: {
      id: string;
      status: "created" | "planning" | "running_tools" | "analyzing" | "waiting_user_input" | "completed" | "cancelling" | "cancelled" | "failed" | "timed_out" | "interrupted";
      user_goal: string;
      provider: string;
      allowed_tools: Array<string>;
      budget: components['schemas']['AgentBudgetDto'];
      current_round: number;
      tool_call_count: number;
      progress: number;
      working_summary: Record<string, unknown>;
      final_output: string;
      failure_code: string;
      failure_message: string;
      cancel_requested: boolean;
      created_at: string;
      started_at: string;
      finished_at: string;
      schema_version: string;
      tool_calls?: Array<components['schemas']['AgentToolCallDto']>;
    }
    AgentToolCallDto: {
      id: string;
      provider_call_id: string;
      tool_name: string;
      tool_version: string;
      status: string;
      arguments_hash: string;
      risk_level: string;
      started_at: string;
      finished_at: string;
      duration_ms: number;
      result_summary: Record<string, unknown>;
      error_code: string;
      error_message: string;
    }
    BaselineMetricResponse: {
      metric: string;
      samples: number;
      median: number;
      latest: number;
      delta: number;
    }
    BaselineResponse: {
      items: Array<components['schemas']['BaselineMetricResponse']>;
    }
    CandidateListResponse: {
      items: Array<components['schemas']['CandidateResponse']>;
    }
    CandidateResponse: {
      item_id: string;
      name: string;
      source_kind: string;
      command_name: string;
      observed_revision: string;
    }
    CapabilityDto: {
      name: string;
      available: boolean;
      reason?: string;
    }
    CleanupResponse: {
      deleted_scans: number;
      deleted_diagnoses: number;
      deleted_log_analyses: number;
      protected_records: number;
      completed_at: string;
    }
    ConfirmDeletionRequest: {
      revision: string;
    }
    ConsentResponse: {
      action: components['schemas']['ActionResponse'];
      ticket: string;
      expires_at: string;
    }
    ContinueDiagnosisRequest: {
      answer: string;
    }
    CpuDto: {
      model: string;
      physical_cores: number;
      logical_cores: number;
      utilization_percent: number;
      frequency_mhz: number;
    }
    CrashGroupDto: {
      application: string;
      faulting_module: string;
      exception_code: string;
      count: number;
      latest_at: string;
      evidence_event_ids: Array<number>;
      providers: Array<string>;
    }
    CreateActionRequest: {
      diagnosis_id: string;
      item_id: string;
      observed_revision: string;
    }
    CreateProcessActionRequest: {
      diagnosis_id: string;
      item_id: string;
      observed_revision: string;
    }
    DeletionImpactResponse: {
      kind: string;
      record_id: string;
      revision: string;
      deletable: boolean;
      dependent_records: number;
      protected_reason: string;
    }
    DeletionResponse: {
      deleted?: boolean;
    }
    DiagnosisFeedbackRequest: {
      helpful: boolean;
      comment?: string;
    }
    DiagnosisListResponse: {
      items: Array<components['schemas']['DiagnosisResponse']>;
    }
    DiagnosisResponse: {
      id: string;
      status: string;
      user_question: string;
      category: string;
      provider: string;
      plan: Array<Record<string, unknown>>;
      diagnosis_plan?: components['schemas']['StructuredDiagnosisPlanDto'];
      agent_round_count?: number;
      max_agent_rounds?: number;
      max_tool_calls?: number;
      stop_reason?: string;
      user_inputs?: Array<string>;
      progress: number;
      current_step: string;
      report: components['schemas']['ReportDto'];
      failure_code: string;
      failure_message: string;
      created_at: string;
      completed_at: string;
      schema_version: string;
      tool_calls?: Array<components['schemas']['ToolCallDto']>;
    }
    DiskDto: {
      volume: string;
      mountpoint: string;
      filesystem: string;
      total_bytes: number;
      free_bytes: number;
      used_bytes: number;
      utilization_percent: number;
    }
    EventEvidenceDto: {
      channel: "Application" | "System";
      provider: string;
      event_id: number;
      level: "critical" | "error" | "warning" | "information";
      timestamp: string;
      summary: string;
      application?: string;
      faulting_module?: string;
      exception_code?: string;
    }
    EventGroupDto: {
      channel: "Application" | "System";
      provider: string;
      event_id: number;
      level: "critical" | "error" | "warning" | "information";
      count: number;
      latest_at: string;
      sample_summary: string;
    }
    EvidenceDetailDto: {
      tool_call_id: string;
      tool_name: string;
      tool_version: string;
      key_fields: Record<string, unknown>;
      raw_result_summary: Record<string, unknown>;
      observed_at?: string;
    }
    EvidenceDto: {
      tool_call_id: string;
      field_path: string;
    }
    ExecuteActionRequest: {
      ticket: string;
    }
    FeedbackAccepted: {
      accepted?: boolean;
    }
    FindingDto: {
      id: string;
      code: string;
      severity: string;
      title: string;
      explanation: string;
      recommendation: string;
      confidence: number;
      evidence: Array<components['schemas']['EvidenceDto']>;
      evidence_details?: Array<components['schemas']['EvidenceDetailDto']>;
    }
    GpuDto: {
      name: string;
      memory_bytes: number;
      driver_version: string;
    }
    HTTPValidationError: {
      detail?: Array<components['schemas']['ValidationError']>;
    }
    HealthResponse: {
      status?: string;
      backend_version: string;
      api_version: string;
      ready: boolean;
    }
    HypothesisDto: {
      id: string;
      key: string;
      hypothesis: string;
      rationale: string;
      supporting_evidence: Array<components['schemas']['EvidenceDto']>;
      contradicting_evidence: Array<components['schemas']['EvidenceDto']>;
      supporting_evidence_details?: Array<components['schemas']['EvidenceDetailDto']>;
      contradicting_evidence_details?: Array<components['schemas']['EvidenceDetailDto']>;
      confidence: number;
      status: string;
    }
    LogAnalysisFailureDto: {
      tool: string;
      code: string;
      message: string;
    }
    LogAnalysisListResponse: {
      items: Array<components['schemas']['LogAnalysisResponse']>;
    }
    LogAnalysisQueryDto: {
      channels: Array<"Application" | "System">;
      lookback_hours: number;
      levels: Array<"critical" | "error" | "warning" | "information">;
      event_ids: Array<number>;
      max_events: number;
    }
    LogAnalysisResponse: {
      id: string;
      status: "queued" | "running" | "completed" | "partial" | "cancelled" | "failed";
      progress: number;
      current_step: string;
      started_at: string;
      finished_at: string;
      query: components['schemas']['LogAnalysisQueryDto'];
      summary: components['schemas']['LogAnalysisSummaryDto'];
      failures: Array<components['schemas']['LogAnalysisFailureDto']>;
      schema_version: string;
    }
    LogAnalysisSummaryDto: {
      event_count: number;
      events: Array<components['schemas']['EventEvidenceDto']>;
      event_groups: Array<components['schemas']['EventGroupDto']>;
      crash_groups: Array<components['schemas']['CrashGroupDto']>;
      notice?: string;
    }
    MemoryDto: {
      total_bytes: number;
      available_bytes: number;
      used_bytes: number;
      utilization_percent: number;
    }
    OperatingSystemDto: {
      name: string;
      version: string;
      build: string;
      architecture: string;
    }
    ProcessCandidateListResponse: {
      items: Array<components['schemas']['ProcessCandidateResponse']>;
    }
    ProcessCandidateResponse: {
      item_id: string;
      name: string;
      source_kind: string;
      command_name: string;
      observed_revision: string;
      cpu_percent: number;
      memory_percent: number;
    }
    ProcessDto: {
      pid: number;
      name: string;
      cpu_percent: number;
      memory_bytes: number;
      memory_percent: number;
    }
    ProviderSettingsResponse: {
      provider: string;
      model: string;
      endpoint: string;
      configured: boolean;
      updated_at: string;
      restart_required?: boolean;
    }
    ProviderTestResponse: {
      succeeded: boolean;
      error_code: string;
      duration_ms: number;
    }
    ReportDto: {
      schema_version: string;
      summary: string;
      category: string;
      findings: Array<components['schemas']['FindingDto']>;
      confidence: number;
      limitations: Array<string>;
      model_explanation: string;
      hypotheses?: Array<components['schemas']['HypothesisDto']>;
    }
    RetentionPolicyResponse: {
      retention_days: number;
    }
    ScanFailureDto: {
      tool: string;
      code: string;
      message: string;
    }
    ScanListResponse: {
      items: Array<components['schemas']['ScanResponse']>;
    }
    ScanResponse: {
      id: string;
      status: "queued" | "running" | "completed" | "partial" | "cancelled" | "failed";
      progress: number;
      current_step: string;
      started_at: string;
      finished_at: string;
      summary: components['schemas']['ScanSummaryDto'];
      failures: Array<components['schemas']['ScanFailureDto']>;
      schema_version: string;
    }
    ScanSummaryDto: {
      capabilities?: Array<components['schemas']['CapabilityDto']>;
      operating_system?: components['schemas']['OperatingSystemDto'];
      cpu?: components['schemas']['CpuDto'];
      gpus?: Array<components['schemas']['GpuDto']>;
      memory?: components['schemas']['MemoryDto'];
      disks?: Array<components['schemas']['DiskDto']>;
      processes?: Array<components['schemas']['ProcessDto']>;
      high_usage_processes?: Array<components['schemas']['ProcessDto']>;
    }
    StartAgentTaskRequest: {
      user_goal: string;
      allowed_tools?: Array<string>;
      budget?: components['schemas']['AgentBudgetRequest'];
    }
    StartDiagnosisRequest: {
      question: string;
    }
    StartLogAnalysisRequest: {
      channels?: Array<"Application" | "System">;
      lookback_hours?: number;
      levels?: Array<"critical" | "error" | "warning" | "information">;
      event_ids?: Array<number>;
      max_events?: number;
    }
    StructuredDiagnosisPlanDto: {
      problem_category: string;
      confidence: number;
      status: string;
      clarification_question: string;
      steps: Array<Record<string, unknown>>;
    }
    ToolCallDto: {
      id: string;
      tool_name: string;
      tool_version: string;
      status: string;
      summary: Record<string, unknown>;
      error_code: string;
      started_at?: string;
      finished_at?: string;
    }
    ToolCatalogResponse: {
      items: Array<components['schemas']['ToolDescriptorDto']>;
    }
    ToolDescriptorDto: {
      name: string;
      version: string;
      qualified_name: string;
      description: string;
      input_schema: Record<string, unknown>;
      risk_level: string;
      sensitivity: Array<string>;
    }
    UpdateProviderSettingsRequest: {
      provider: string;
      model: string;
      endpoint: string;
      api_key?: string;
    }
    UpdateRetentionPolicyRequest: {
      retention_days: number;
    }
    ValidationError: {
      loc: Array<string | number>;
      msg: string;
      type: string;
      input?: unknown;
      ctx?: Record<string, unknown>;
    }
  };
};
