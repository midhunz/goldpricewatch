"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Loader2, ExternalLink, Newspaper, Calendar, Building2 } from "lucide-react";
import Image from "next/image";

interface NewsArticle {
    id: number;
    title: string;
    summary: string;
    source: string;
    url: string;
    image_url: string | null;
    slug: string;
    published_at: string | null;
}

import { useRouter } from "next/navigation";

export default function GoldNewsPage() {
    const router = useRouter();
    const [news, setNews] = useState<NewsArticle[]>([]);
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        async function fetchNews() {
            try {
                const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/news`);
                if (res.ok) {
                    const data = await res.json();
                    setNews(data);
                }
            } catch (error) {
                console.error("Failed to fetch news", error);
            } finally {
                setIsLoading(false);
            }
        }

        fetchNews();
    }, []);

    const formatDate = (dateString: string | null) => {
        if (!dateString) return "Recently";
        const date = new Date(dateString);
        const now = new Date();
        const diffMs = now.getTime() - date.getTime();
        const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
        const diffDays = Math.floor(diffHours / 24);

        if (diffHours < 1) return "Just now";
        if (diffHours < 24) return `${diffHours}h ago`;
        if (diffDays === 1) return "Yesterday";
        if (diffDays < 7) return `${diffDays} days ago`;

        return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
    };

    if (isLoading) {
        return (
            <div className="container py-20 flex justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-yellow-500" />
            </div>
        );
    }

    return (
        <div className="container mx-auto py-10 px-4 max-w-6xl">
            <div className="flex flex-col items-center text-center space-y-4 mb-10">
                <h1 className="text-4xl font-bold tracking-tight flex items-center gap-2">
                    <Newspaper className="h-8 w-8 text-yellow-500" />
                    Gold News Today
                </h1>
                <p className="text-muted-foreground max-w-2xl">
                    Stay updated with the latest gold market news, price movements, and investment insights.
                </p>
            </div>

            {news.length === 0 ? (
                <div className="text-center py-20 text-muted-foreground">
                    <Newspaper className="h-16 w-16 mx-auto mb-4 opacity-20" />
                    <p>No news articles available yet.</p>
                    <p className="text-sm mt-2">Check back soon for updates!</p>
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {news.map((article) => (
                        <Card
                            key={article.id}
                            className="border-white/10 bg-card/50 backdrop-blur hover:border-yellow-500/50 transition-all cursor-pointer group"
                            onClick={() => router.push(`/gold-news-today/${article.slug}`)}
                        >
                            {article.image_url && (
                                <div className="relative h-48 w-full overflow-hidden rounded-t-lg">
                                    <img
                                        src={article.image_url}
                                        alt={article.title}
                                        className="object-cover w-full h-full group-hover:scale-105 transition-transform duration-300"
                                    />
                                </div>
                            )}
                            <CardHeader>
                                <CardTitle className="text-lg line-clamp-2 group-hover:text-yellow-500 transition-colors">
                                    {article.title}
                                </CardTitle>
                                <div className="flex items-center gap-4 text-xs text-muted-foreground mt-2">
                                    <div className="flex items-center gap-1">
                                        <Building2 className="h-3 w-3" />
                                        {article.source}
                                    </div>
                                    <div className="flex items-center gap-1">
                                        <Calendar className="h-3 w-3" />
                                        {formatDate(article.published_at)}
                                    </div>
                                </div>
                            </CardHeader>
                            <CardContent>
                                <p className="text-sm text-muted-foreground line-clamp-3">
                                    {article.summary}
                                </p>
                                <div className="flex items-center gap-2 mt-4 text-yellow-500 text-sm font-medium">
                                    Read Summary <ExternalLink className="h-4 w-4" />
                                </div>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            )}
        </div>
    );
}
