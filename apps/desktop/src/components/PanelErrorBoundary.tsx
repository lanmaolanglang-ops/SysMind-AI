import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  name: string;
}

interface State {
  failed: boolean;
  generation: number;
}

export class PanelErrorBoundary extends Component<Props, State> {
  state: State = { failed: false, generation: 0 };

  static getDerivedStateFromError(): Partial<State> {
    return { failed: true };
  }

  componentDidCatch() {
    // React reports details in development; no user or provider data is copied into UI logs here.
  }

  render() {
    if (this.state.failed) {
      return (
        <section className="panel-error" role="alert">
          <h2>{this.props.name}暂时不可用</h2>
          <p>该面板发生异常，其他诊断功能仍可继续使用。重新加载不会重复提交状态变更。</p>
          <button
            type="button"
            onClick={() =>
              this.setState((state) => ({ failed: false, generation: state.generation + 1 }))
            }
          >
            重新加载此面板
          </button>
        </section>
      );
    }
    return <div key={this.state.generation}>{this.props.children}</div>;
  }
}
