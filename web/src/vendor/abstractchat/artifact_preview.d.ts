import React from "react";
import { type AfFileViewerKind, type AfGatewayFetch } from "@abstractframework/ui-kit";
/** Enforce the cap even when a response has no Content-Length. */
export declare function boundedPreviewBlob(response: Response, limit?: number): Promise<Blob>;
export declare function artifactPreviewKind(name: string, type: string): AfFileViewerKind;
export declare function ArtifactPreviewModal(p: {
    name: string;
    path: string;
    fetchGateway: AfGatewayFetch;
    onClose: () => void;
}): React.ReactElement;
//# sourceMappingURL=artifact_preview.d.ts.map