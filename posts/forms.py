from django import forms
from .models import Post, Comment, Category, Tag

class PostForm(forms.ModelForm):
    tags = forms.CharField(
        max_length=200, 
        required=False, 
        help_text='Enter tags separated by commas',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter tags separated by commas'})
    )
    
    class Meta:
        model = Post
        fields = ['text', 'image', 'category']
        widgets = {
            'text': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 4, 
                'placeholder': 'What\'s on your mind?'
            }),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
        }
    
    def clean_tags(self):
        tags = self.cleaned_data.get('tags', '')
        if tags:
            tag_names = [tag.strip() for tag in tags.split(',') if tag.strip()]
            return tag_names
        return []

class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['text']