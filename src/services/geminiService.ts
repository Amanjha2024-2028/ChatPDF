const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export interface ChatSession {
    sendMessage: (message: string) => Promise<string>;
}

export async function uploadPdf(file: File): Promise<string> {
    try {
        const formData = new FormData();
        formData.append('file', file);

        console.log('Uploading to:', `${API_BASE_URL}/upload`);

        const response = await fetch(`${API_BASE_URL}/upload`, {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            let errorDetail = 'Failed to upload PDF';
            try {
                const error = await response.json();
                errorDetail = error.detail || errorDetail;
            } catch {
                errorDetail = `HTTP ${response.status}: ${response.statusText}`;
            }
            throw new Error(errorDetail);
        }
        
        const data = await response.json();
        if (!data.doc_id) {
            throw new Error("Server did not return a document ID");
        }
        console.log('Upload successful, doc_id:', data.doc_id);
        return data.doc_id;
    } catch (error) {
        console.error('Upload error:', error);
        if (error instanceof Error) {
            throw error;
        }
        throw new Error('Network error occurred while uploading PDF');
    }
}

export async function queryPdf(query: string, doc_id: string): Promise<string> {
    try {
        console.log('Querying:', `${API_BASE_URL}/query`);
        
        const response = await fetch(`${API_BASE_URL}/query`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ query, doc_id }),
        });

        if (!response.ok) {
            let errorDetail = 'Failed to query PDF';
            try {
                const error = await response.json();
                errorDetail = error.detail || errorDetail;
            } catch {
                errorDetail = `HTTP ${response.status}: ${response.statusText}`;
            }
            throw new Error(errorDetail);
        }

        const data = await response.json();
        return data.answer;
    } catch (error) {
        console.error('Query error:', error);
        if (error instanceof Error) {
            throw error;
        }
        throw new Error('Network error occurred while querying PDF');
    }
}

export async function createChatSession(doc_id: string): Promise<ChatSession> {
    return {
        sendMessage: async (message: string) => {
            return await queryPdf(message, doc_id);
        }
    };
}
