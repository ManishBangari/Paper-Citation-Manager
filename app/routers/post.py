from typing import Optional

from .. import models, schemas, oauth2 
from fastapi import  Response, status, HTTPException, Depends, APIRouter
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db  


router = APIRouter(
    prefix="/posts",
    tags=['Posts']
)

@router.get("/", response_model=list[schemas.PostOut])
def get_posts(db: Session = Depends(get_db), current_user: int = Depends(oauth2.get_current_user), limit: int = 10, skip: int = 0, search: Optional[str] = ""):
    #cursor.execute("""SELECT * FROM posts""")
    #posts = cursor.fetchall()
    #print(limit)
    #print(search)
    #posts = db.query(models.Post).filter(models.Post.title.contains(search)).limit(limit).offset(skip).all()

    results = db.query(models.Post, func.count(models.Vote.post_id).label("votes")).join(models.Vote, models.Vote.post_id == models.Post.id, isouter=True).group_by(models.Post.id).filter(models.Post.title.contains(search)).limit(limit).offset(skip).all()

    #print(result)
    #print(posts)
    return results

@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.Post) 
#async def create_posts(payload: dict = Body(...)): // previous method to get the data from the body of the request
def create_posts(post: schemas.PostCreate, db: Session = Depends(get_db), current_user: int = Depends(oauth2.get_current_user)):
    #print(post)
    #print(post.dict())

    #post_dict = post.dict()
    #post_dict['id'] = randrange(0, 10000)
    
    #my_posts.append(post_dict)
    #cursor.execute("""INSERT INTO posts (title, content, published) VALUES (%s, %s, %s) RETURNING * """, (post.title, post.content, post.published))
    #new_post = cursor.fetchone()

    #conn.commit()
    #print(**post.dict())
    #new_post = models.Post(title=post.title, content=post.content, published=post.published)
    #print(current_user.id)
    new_post = models.Post(**post.dict(), owner_id=current_user.id)
    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    return new_post

# title str, content str, categoory, etc...
@router.get("/{id}", response_model=schemas.PostOut)
def get_post(id: int, db: Session = Depends(get_db), current_user: int = Depends(oauth2.get_current_user)):
   #cursor.execute("""SELECT * FROM posts WHERE id = %s """, (str(id), ))
   #post = cursor.fetchone()

   #print(post)
   #print(type(id))
   #post = find_post(id)

   post = db.query(models.Post, func.count(models.Vote.post_id).label("votes")).join(models.Vote, models.Vote.post_id == models.Post.id, isouter=True).group_by(models.Post.id).filter(models.Post.id == id).first()

   if not post:
       #reponse.status_code = status.HTTP_404_NOT_FOUND
       #return {"message": f"post with id: {id} was not found"}
       raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                           detail=f"post with id: {id} was not found")
   
   return post

def find_index_post(id):
    for i, p in enumerate(my_posts):
        if p['id'] == id:
            return i
    
@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(id: int, db: Session = Depends(get_db), current_user: int = Depends(oauth2.get_current_user)):

    #cursor.execute("DELETE FROM posts WHERE id = %s RETURNING *",(id,))

    #deleted_post = cursor.fetchone()

    post = db.query(models.Post).filter(models.Post.id == id)
    if post.first() == None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post with id {id} does not exist"
        )

    if post.first().owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to perform requested action")
    
    #conn.commit()
    post.delete(synchronize_session=False)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.put("/{id}", response_model=schemas.Post)
def update_posts(id: int, post:schemas.PostCreate, db: Session = Depends(get_db), current_user: int = Depends(oauth2.get_current_user)):
    #print(post)
    #cursor.execute("UPDATE posts SET title = %s, content = %s, published = %s WHERE id = %s RETURNING *",(post.title, post.content, post.published, id))

    #updated_post = cursor.fetchone()
    #index = find_index_post(id)

    post_query = db.query(models.Post).filter(models.Post.id == id)
    if post_query.first() == None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, 
                            detail=f"post with id: {id} does not exist")

    if post_query.first().owner_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to perform requested action")
    
    post_query.update(post.dict(), synchronize_session=False)
    #conn.commit()
    #post_dict = post.dict()
    #post_dict['id'] = id
    #my_posts[updated_post] = post_dict
    db.commit()
    return post_query.first()