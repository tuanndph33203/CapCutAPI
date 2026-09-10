import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "./ui/button";

interface Props {
  children?: ReactNode;
  fallbackTitle?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("ErrorBoundary caught an error:", error, errorInfo);
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null });
    window.location.reload();
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center p-8 m-4 rounded-2xl bg-zinc-900 border border-red-500/30 text-center space-y-4 max-w-xl mx-auto shadow-2xl">
          <div className="w-12 h-12 rounded-full bg-red-500/10 border border-red-500/20 flex items-center justify-center text-red-400">
            <AlertTriangle className="w-6 h-6" />
          </div>
          <div className="space-y-1">
            <h3 className="text-base font-bold text-zinc-100">
              {this.props.fallbackTitle || "Đã xảy ra lỗi hiển thị giao diện"}
            </h3>
            <p className="text-xs text-zinc-400">
              Hệ thống đã tự động ngăn chặn trang bị trắng. Chi tiết:
            </p>
          </div>
          <div className="p-3 bg-black/60 border border-zinc-800 rounded-lg text-left w-full overflow-x-auto">
            <code className="text-xs text-red-400 font-mono">
              {this.state.error?.message || String(this.state.error)}
            </code>
          </div>
          <div className="flex gap-3">
            <Button
              onClick={this.handleReset}
              className="bg-amber-500 hover:bg-amber-600 text-zinc-950 font-bold text-xs gap-2"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Tải lại trang
            </Button>
            <Button
              variant="outline"
              onClick={() => this.setState({ hasError: false, error: null })}
              className="text-xs text-zinc-300 border-zinc-700"
            >
              Bỏ qua & Tiếp tục
            </Button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
