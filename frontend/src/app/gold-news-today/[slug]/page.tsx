"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Loader2, ExternalLink, Calendar, Building2, ArrowLeft, Share2 } from "lucide-react";
import Link from "next/link";

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

export default function NewsDetailPage() {
    const params = useParams();
    const [article, setArticle] = useState<NewsArticle | null>(null);
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        async function fetchArticle() {
            if (!params.slug) return;

            try {
                const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/news/${params.slug}`);
                if (res.ok) {
                    const data = await res.json();
                    setArticle(data);
                }
            } catch (error) {
                console.error("Failed to fetch article", error);
            } finally {
                setIsLoading(false);
            }
        }

        fetchArticle();
    }, [params.slug]);

    const formatDate = (dateString: string | null) => {
        if (!dateString) return "";
        return new Date(dateString).toLocaleDateString(undefined, {
            weekday: 'long',
            year: 'numeric',
            month: 'long',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    };

    if (isLoading) {
        return (
            <div className="container py-20 flex justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-yellow-500" />
            </div>
        );
    }

    if (!article) {
        return (
            <div className="container py-20 text-center">
                <h1 className="text-2xl font-bold mb-4">Article Not Found</h1>
                <Link href="/gold-news-today">
                    <Button variant="outline">Back to News</Button>
                </Link>
            </div>
        );
    }

    return (
        <div className="container mx-auto py-10 px-4 max-w-4xl">
            <Link href="/gold-news-today" className="inline-flex items-center text-muted-foreground hover:text-yellow-500 mb-6 transition-colors">
                <ArrowLeft className="h-4 w-4 mr-2" />
                Back to News
            </Link>

            <article className="space-y-8">
                {/* Header */}
                <div className="space-y-4">
                    <h1 className="text-3xl md:text-4xl lg:text-5xl font-bold tracking-tight leading-tight">
                        {article.title}
                    </h1>

                    <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground border-b border-white/10 pb-6">
                        <div className="flex items-center gap-2">
                            <Building2 className="h-4 w-4 text-yellow-500" />
                            <span className="font-medium text-foreground">{article.source}</span>
                        </div>
                        <div className="flex items-center gap-2">
                            <Calendar className="h-4 w-4" />
                            {formatDate(article.published_at)}
                        </div>
                    </div>
                </div>

                {/* Hero Image */}
                {article.image_url && (
                    <div className="relative w-full aspect-video rounded-xl overflow-hidden border border-white/10 bg-card/50">
                        <img
                            src={article.image_url}
                            alt={article.title}
                            className="object-cover w-full h-full"
                        />
                    </div>
                )}

                {/* Content */}
                <div className="prose prose-invert max-w-none">
                    <div className="text-lg leading-relaxed text-muted-foreground"
                        dangerouslySetInnerHTML={{ __html: article.summary }} />
                </div>

                {/* Actions */}
                <div className="flex flex-col sm:flex-row gap-4 pt-8 border-t border-white/10">
                    <Button
                        size="lg"
                        className="bg-yellow-500 hover:bg-yellow-600 text-black font-bold gap-2"
                        onClick={() => window.open(article.url, '_blank')}
                    >
                        Read Full Article on {article.source}
                        <ExternalLink className="h-4 w-4" />
                    </Button>

                    <Button variant="outline" size="lg" className="gap-2">
                        <Share2 className="h-4 w-4" />
                        Share Article
                    </Button>
                </div>
            </article>
        </div>
    );
}
